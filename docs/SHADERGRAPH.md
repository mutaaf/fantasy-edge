# Shader Graph, written as text

RealityKit's Shader Graph materials are MaterialX node networks stored in USD.
Reality Composer Pro is only an editor for them. The file it saves is plain
`.usda`, so a specialist can write one by hand, compile it headlessly with
`xcrun realitytool`, and load it in the app. No GUI is involved at any step.

## The pipeline

```
tools/shadergraph/Materials.rkassets/<Name>.usda   hand-written MaterialX networks
        │  python3 tools/shadergraph/build.py        (xcrun realitytool compile … --platform xrsimulator|xros)
        ▼
assets/generated/shadergraph/Materials.reality      one compiled package; bundled with assets/
        │  design/tokens.json → shaderGraph.materials.<id> = {file, prim, parameters, fallback}
        ▼
StadiumShaderGraph.material(prim, file:)             loads once, returns a copy
StadiumShaderGraph.set(&material, name, tokenValue)  "#RRGGBB" → colour, number → float
```

- **Run the build per platform.** `build.py` defaults to `xrsimulator`; pass `xros` for a device build. The two outputs were byte-identical for the proof material.
- **Commit the compiled `.reality`.** The app build does not run realitytool.

## Writing a material

Use `tools/shadergraph/Materials.rkassets/Fresnel.usda` as the template:

- **One `def Material`.** Its `inputs:` are the parameters, and `outputs:mtlx:surface.connect` points at a surface shader.
- **One `def Shader` per node.** Set `uniform token info:id = "ND_…"`, typed `inputs:` (literal, or `.connect = </path.outputs:out>`), and a typed `outputs:out`.
- **A bound mesh named `<Material>Preview`** (`FresnelPreview` for `/Root/Fresnel`). The loader finds a material by the mesh bound to it, because RealityKit keeps no material name. Compilation also drops any material no mesh uses. A file holding a single graph material may keep a mesh called plain `Preview`.

### One file per actor, as many materials as it needs

This is the canonical layout. Lighting's `Beams.reality` is the model.

- **Where it lives:** an actor's graphs go in its own `tools/blender/<actor>/shadergraph/<Name>.rkassets` and compile to `assets/actors/<actor>/<Name>.reality`. That keeps the actor's merges off everyone else's files.
- **Several materials:** put them in that one `.usda`, each with its own `<Material>Preview` mesh. The loader opens each file once.
- **Shared materials:** `tools/shadergraph/Materials.rkassets` holds only materials more than one actor uses, such as `Fresnel`. The director owns it.
- **Tokens:** `file` names the `.reality`, and `prim` names the material (`/Root/<Material>`).
- **Material inputs are the parameters `setParameter(name:)` sees.** `inputs:Opacity` is set with `"Opacity"`.

### Node ids used and compiled

| Node | id |
|---|---|
| Unlit surface | `ND_realitykit_unlit_surfaceshader` (`color`, `opacity`, `applyPostProcessToneMap`, `hasPremultipliedAlpha`) |
| World normal | `ND_normal_vector3` (`space = "world"`) |
| View direction | `ND_realitykit_viewdirection_vector3` |
| Maths | `ND_dotproduct_vector3`, `ND_absval_float`, `ND_subtract_float`, `ND_power_float`, `ND_mix_float`, `ND_multiply_float` |

Other ids should work but are untried here:
- The PBR surface: `ND_realitykit_pbr_surfaceshader`.
- The rest of the standard MaterialX library (`ND_image_color3`, `ND_texcoord_vector2`, `ND_time_float`, `ND_sin_float`, `ND_clamp_float`, `ND_smoothstep_float` …).
- `ND_realitykit_geometry_modifier_vertexshader`, for vertex motion such as crowd sway or net billow.

Add a row to the table above once a node has rendered in a shot.

### Failure modes

- **Compilation does not validate.** `realitytool compile` accepted the package silently and printed nothing. A wrong `info:id`, a type mismatch or a broken connection compiles, then fails at load.
- **Check the load in the log.** After any change, grep the app log for `[shadergraph]`, and shoot it.
- **A material bound to no mesh is compiled out.**
- **Several graph materials in one file and no `<Material>Preview` mesh:** the loader refuses to guess. It logs the mesh names it did find and returns nil, so the actor draws its fallback.
- **No scene depth.** RealityKit's MaterialX has no scene-depth input, so there is no true soft-particle or depth fade where a beam or sprite meets geometry. Fade by view angle (as `Beam` does) or by distance from the camera instead.
- **Model the named API as unsupported.** `ShaderGraphMaterial(named:from:in:)` looks for the scene inside Reality Composer Pro content that Xcode compiled into a Swift package bundle, not in a loose `.reality`. `StadiumShaderGraph` tries it first and logs which path loaded. On this project's generated Xcode target, expect the fallback: `Entity(contentsOf:)` on the `.reality`, then read the material off the model.

## Tokens and the portable fallback

Every Shader Graph material has an entry under `shaderGraph.materials` in `design/tokens.json`. The scene embeds it as `scene.shaderGraph`.

```json
"fresnel": {
  "file": "generated/shadergraph/Materials.reality",
  "prim": "/Root/Fresnel",
  "parameters": {"Color": "#9FD8FF", "Opacity": 0.85, "Power": 2.5, "Invert": 0},
  "fallback":   {"blend": "alpha", "color": "#9FD8FF", "opacity": 0.3}
}
```

- **`parameters`** are what the headset sets. A web or Android renderer that reimplements the graph in its own shader language reads the same values:
  - Three.js: `onBeforeCompile` or a `ShaderMaterial`.
  - Filament: a `.mat` material.
- **`fallback`** is what any client draws when it has no Shader Graph: the web and Android ports before they port the shader, or a headset load failure. It must be expressible as a plain blended or additive unlit material: `blend`, `color`, `opacity`.
- **Actors reference an entry by id** from their own `visual.<actor>` section, for example `"netMaterial": "fresnel"`. They never duplicate the parameters.
- **Keep the math in the `.usda` simple enough to port.** A graph the ports can't reproduce should say so in its fallback, not silently look different.

## Proof

- **Launch argument:** `-shaderGraphProof` puts three spheres over midfield, left to right:
  1. The tokens-driven Fresnel material.
  2. The same material with `Invert = 1`, set at runtime.
  3. The fallback.
- **Shot:** `EXTRA=-shaderGraphProof SUFFIX=-sg` with `redzone-trails`. See `docs/lookdev/integration-4/s-redzone-trails-sg.png`.
- **Result, integration-4 at 6dde102 on the xrsimulator: it renders.**
  1. Left: a clear centre with a bright rim, the Fresnel falloff.
  2. Middle: a solid centre fading at the edge, which proves `setParameter("Invert")` works at runtime.
  3. Right: the flat translucent fallback, visibly different.

  An unlit colour cannot draw the rim, so the graph compiled, loaded, and took its token parameters.
- **Load path, confirmed at integration-5:** `[shadergraph] /Root/Fresnel loaded from generated/shadergraph/Materials.reality via Entity(contentsOf:)`. As expected, the named API found nothing, so the app loads through the fallback.

## Who is waiting on this

| Actor | Needs |
|---|---|
| Field | Paint grass breakup |
| Sideline | Net view-angle falloff, a direct use of `Fresnel` |
| Lighting | Adopted at a4c96e6: `Beam` in `assets/actors/lighting/Beams.reality` (dust on built-in time, view-angle falloff); the UV scroll stays as the fallback |
| Crowd | Animated impostors, via the geometry modifier |
| Moments | Particle sprites |
