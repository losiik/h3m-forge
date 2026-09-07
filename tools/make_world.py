"""python tools/make_world.py examples/archipelago.json --output out/archipelago.h3m"""

import argparse
import json
from pathlib import Path

from h3m import mapfile, paths
from h3m.world import Assets, WorldSpec, generate_world


def main():
    parser = argparse.ArgumentParser(description="Generate a native HotA world from a zone specification")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, default=Path("out/world.h3m"))
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    value = json.loads(args.spec.read_text(encoding="utf-8"))
    if args.seed is not None:
        value["seed"] = args.seed
    spec = WorldSpec.from_dict(value)
    print("Reading terrain and object references from installed maps...", flush=True)
    assets = Assets.cached(list(paths.iter_maps()), paths.out_dir() / "world-assets.json")
    print("Generating and validating world...", flush=True)
    world = generate_world(spec, assets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mapfile.save(args.output, world.map)
    report_path = args.output.with_suffix(".report.json")
    report_path.write_text(json.dumps(world.report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(world.report, ensure_ascii=False, indent=2))
    print(f"Map: {args.output.resolve()}")


if __name__ == "__main__":
    main()
