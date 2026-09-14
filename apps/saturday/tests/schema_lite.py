"""The subset of JSON Schema 2020-12 the contracts use, validated with stdlib.

Supported: type (including unions), const, enum, required, properties, items,
allOf, anyOf, $ref (same file or sibling file), minimum, maximum, minLength,
pattern. An unsupported keyword raises, so a contract can never silently use
something this validator ignores.
"""
from __future__ import annotations

import json
import pathlib
import re

KNOWN = {"$schema", "$id", "$defs", "title", "description", "type", "const", "enum", "required",
         "properties", "items", "allOf", "anyOf", "$ref", "minimum", "maximum", "minLength", "pattern"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


class Validator:
    def __init__(self, folder: pathlib.Path):
        self.folder = folder
        self.docs: dict[str, dict] = {}

    def doc(self, name: str) -> dict:
        if name not in self.docs:
            self.docs[name] = json.loads((self.folder / name).read_text())
        return self.docs[name]

    def resolve(self, ref: str, base: str):
        file, _, pointer = ref.partition("#")
        file = file or base
        node = self.doc(file)
        for part in [p for p in pointer.split("/") if p]:
            node = node[part]
        return node, file

    def errors(self, value, schema: dict, base: str, path: str = "$") -> list[str]:
        unknown = set(schema) - KNOWN
        if unknown:
            raise ValueError(f"{base}: unsupported keywords {sorted(unknown)} at {path}")
        out: list[str] = []
        if "$ref" in schema:
            target, file = self.resolve(schema["$ref"], base)
            out += self.errors(value, target, file, path)
        for sub in schema.get("allOf", []):
            out += self.errors(value, sub, base, path)
        if "anyOf" in schema and all(self.errors(value, s, base, path) for s in schema["anyOf"]):
            out.append(f"{path}: matches none of anyOf")
        if "type" in schema:
            types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_is(value, t) for t in types):
                return out + [f"{path}: expected {types}, got {type(value).__name__}"]
        if "const" in schema and value != schema["const"]:
            out.append(f"{path}: expected const {schema['const']!r}")
        if "enum" in schema and value not in schema["enum"]:
            out.append(f"{path}: {value!r} not in {schema['enum']}")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    out.append(f"{path}: missing {key}")
            for key, sub in schema.get("properties", {}).items():
                if key in value:
                    out += self.errors(value[key], sub, base, f"{path}.{key}")
        if isinstance(value, list) and "items" in schema:
            for i, item in enumerate(value):
                out += self.errors(item, schema["items"], base, f"{path}[{i}]")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                out.append(f"{path}: {value} < {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                out.append(f"{path}: {value} > {schema['maximum']}")
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append(f"{path}: shorter than {schema['minLength']}")
            if "pattern" in schema and not re.search(schema["pattern"], value):
                out.append(f"{path}: {value!r} does not match {schema['pattern']}")
        return out

    def validate(self, value, name: str) -> list[str]:
        return self.errors(value, self.doc(name), name)
