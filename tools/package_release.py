"""Build a reproducible, allowlisted marketplace ZIP. No external dependencies."""

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def build(output_dir=None):
    version = json.loads((ROOT / "plugins/archlens/.claude-plugin/plugin.json").read_text())["version"]
    output = Path(output_dir) if output_dir else ROOT / "dist"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"archlens-{version}.zip"
    inputs = [ROOT / name for name in (
        "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
        "CODE_OF_CONDUCT.md", "SUPPORT.md", "GOVERNANCE.md", "CITATION.cff",
        "package.json", "package-lock.json",
    )]
    for name in (".claude-plugin", "plugins", "skills", "docs", "examples", "tools", "tests"):
        inputs.extend(
            path for path in (ROOT / name).rglob("*")
            if path.is_file() and (path.suffix in {".md", ".json", ".py", ".mjs"} or path.name == "LICENSE")
        )
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(inputs):
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError(f"Refusing a linked release input: {path}")
            relative = path.relative_to(ROOT).as_posix()
            if "__pycache__" in path.parts:
                continue
            info = zipfile.ZipInfo(f"archlens-{version}/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive


if __name__ == "__main__":
    print(build())
