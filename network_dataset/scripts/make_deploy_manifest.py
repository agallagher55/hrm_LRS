"""
Write data/deploy_manifest.json from the files in this repo.

Run it after changing any script in network_dataset/scripts or qa_refresh, or the network template,
and commit the result. deploy_check.py compares the files on the T: drive with it.
"""

import json

import deploy_check


def main():
    manifest = deploy_check.build_manifest(deploy_check.ROOT)
    deploy_check.MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {deploy_check.MANIFEST_PATH} with {len(manifest['files'])} files.")


if __name__ == "__main__":
    main()
