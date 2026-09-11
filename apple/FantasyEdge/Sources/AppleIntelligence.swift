import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

/// The on-device narrator.
///
/// `FoundationModels` is Swift-only: there is no way to reach it from the
/// Python that computes the brief, and no HTTP endpoint in front of it. So the
/// headset writes the prose and posts it back to `/api/intel/narrate`, where
/// it goes through exactly the verification, labelling and payload slot a
/// cloud model's output goes through. This side gets no privileged path.
///
/// Everything is behind `canImport` and a runtime availability check because
/// the app's deployment target is visionOS 2.0 and the framework arrived in
/// 26. Compiled against an older SDK the whole thing folds down to
/// `.notBuilt`, which is a sentence on screen rather than a build failure.
enum AppleIntelligence {

    /// What the device can actually do, in the shape the view needs.
    ///
    /// Apple reports device support, Apple Intelligence being switched off,
    /// and model assets still downloading as three distinct cases, and they
    /// want three distinct sentences: only one of them is worth the reader
    /// doing anything about. None of them is an error - the computed brief
    /// underneath is complete either way, which is why these read like the
    /// `no_key` state the cloud providers return rather than like a failure.
    enum Readiness: Equatable {
        case ready
        case notBuilt
        case unsupportedDevice
        case switchedOff
        case downloading
        case unknown

        var usable: Bool { self == .ready }

        var line: String {
            switch self {
            case .ready:
                return "Apple Intelligence is ready on this device."
            case .notBuilt:
                return "This build has no on-device model framework, so there "
                     + "is nothing here to write prose with. Everything below "
                     + "is computed and complete without one."
            case .unsupportedDevice:
                return "This device is not eligible for Apple Intelligence, so "
                     + "there is no on-device model to narrate with. Everything "
                     + "below is computed and complete without one."
            case .switchedOff:
                return "Apple Intelligence is switched off. Turn it on in "
                     + "Settings if you want a written summary; the findings "
                     + "below do not need one."
            case .downloading:
                return "Apple Intelligence is still downloading its model. Try "
                     + "again once it has finished; nothing below is waiting "
                     + "on it."
            case .unknown:
                return "The on-device model reported a state this app does not "
                     + "recognise. The findings below are computed and do not "
                     + "depend on it."
            }
        }
    }

    static var readiness: Readiness {
        #if canImport(FoundationModels)
        if #available(visionOS 26.0, iOS 26.0, macOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                return .ready
            case .unavailable(.deviceNotEligible):
                return .unsupportedDevice
            case .unavailable(.appleIntelligenceNotEnabled):
                return .switchedOff
            case .unavailable(.modelNotReady):
                return .downloading
            @unknown default:
                return .unknown
            }
        }
        return .unsupportedDevice
        #else
        return .notBuilt
        #endif
    }

    /// A short name for what wrote the text, for the line beside the prose.
    static var modelName: String { "Apple Foundation Models, on device" }

    struct Refused: LocalizedError {
        let why: String
        var errorDescription: String? { why }
    }

    /// Run the model on the prompt the brief supplied.
    ///
    /// `system` and `user` come from `narration.prompt` and are passed through
    /// untouched. Building a prompt here out of rosters or scores would break
    /// the one guarantee that makes model prose safe to show at all: a
    /// narrator that has only seen findings can get the emphasis wrong, which
    /// a reader can correct from the cards below; a narrator that has seen the
    /// raw payload can find a number nobody computed.
    static func write(system: String, user: String) async throws -> String {
        #if canImport(FoundationModels)
        if #available(visionOS 26.0, iOS 26.0, macOS 26.0, *) {
            let session = LanguageModelSession(instructions: system)
            do {
                let reply = try await session.respond(
                    to: user,
                    // Low temperature and a hard ceiling on length. The system
                    // instruction asks for three to five sentences; a token
                    // budget is what makes that a limit rather than a request,
                    // and on a headset every token is battery and heat.
                    options: GenerationOptions(temperature: 0.3,
                                               maximumResponseTokens: 320))
                return reply.content
            } catch let e as LanguageModelSession.GenerationError {
                throw Refused(why: plain(e))
            }
        }
        throw Refused(why: readiness.line)
        #else
        throw Refused(why: readiness.line)
        #endif
    }

    #if canImport(FoundationModels)
    /// The framework's own errors, said in the register the rest of this view
    /// uses. `localizedDescription` on several of these carries the prompt
    /// back with it, and a wall of findings pasted into an error box is not an
    /// explanation.
    @available(visionOS 26.0, iOS 26.0, macOS 26.0, *)
    private static func plain(_ e: LanguageModelSession.GenerationError) -> String {
        switch e {
        case .exceededContextWindowSize:
            return "There are more findings than the on-device model can read "
                 + "at once. They are all below; it could not summarise them."
        case .assetsUnavailable:
            return "The on-device model's assets are not on this device yet."
        case .guardrailViolation:
            return "The on-device model declined to write this up. Nothing "
                 + "below depends on it."
        case .rateLimited:
            return "The on-device model is rate limited right now. Try again "
                 + "in a moment."
        case .concurrentRequests:
            return "The on-device model is already busy with another request."
        case .unsupportedLanguageOrLocale:
            return "The on-device model does not support this device's "
                 + "language."
        case .refusal:
            return "The on-device model refused the request."
        default:
            return "The on-device model could not complete the request."
        }
    }
    #endif
}
