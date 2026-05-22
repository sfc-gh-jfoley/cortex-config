"""Copy the Snowflake Slides template to a target Drive folder."""
import argparse, json, sys, os
from pathlib import Path

import google.auth, google.auth.transport.requests
from googleapiclient.discovery import build
import yaml


def _load_config():
    cfg_path = Path(__file__).parent.parent / "config" / "snowflake-gslides-config.yaml"
    if cfg_path.exists():
        with open(cfg_path) as f:
            return yaml.safe_load(f)
    return {}


def _resolve_folder_path(drive_svc, path_parts):
    parent_id = "root"
    for part in path_parts:
        q = f"'{parent_id}' in parents and name='{part}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_svc.files().list(q=q, fields="files(id, name)", pageSize=5).execute()
        files = results.get("files", [])
        if not files:
            return None, part
        parent_id = files[0]["id"]
    return parent_id, None


def main():
    parser = argparse.ArgumentParser(description="Copy Snowflake Slides template")
    parser.add_argument("--name", required=True, help="Name for the new presentation")
    parser.add_argument("--folder-id", help="Target Drive folder ID")
    parser.add_argument("--folder-path", help="Drive folder path relative to My Drive (e.g. '99.temp/20260513_test1')")
    parser.add_argument("--template-id", help="Override template_id from config")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    cfg = _load_config()
    template_id = args.template_id or cfg.get("template_id")
    if not template_id:
        print("ERROR: No template_id specified (--template-id or config.yaml)", file=sys.stderr)
        sys.exit(1)

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    drive_svc = build("drive", "v3", credentials=creds)

    folder_id = args.folder_id
    if not folder_id and args.folder_path:
        parts = [p for p in args.folder_path.split("/") if p]
        folder_id, missing = _resolve_folder_path(drive_svc, parts)
        if folder_id is None:
            print(f"ERROR: Folder '{missing}' not found via Drive API.", file=sys.stderr)
            print("Drive Desktop sync may be pending. Check sync status or provide --folder-id directly.", file=sys.stderr)
            sys.exit(2)

    body = {"name": args.name}
    if folder_id:
        body["parents"] = [folder_id]

    result = drive_svc.files().copy(fileId=template_id, body=body, fields="id, name, webViewLink").execute()

    output = {
        "presentation_id": result["id"],
        "name": result["name"],
        "url": result.get("webViewLink", f"https://docs.google.com/presentation/d/{result['id']}/edit"),
    }
    if folder_id:
        output["folder_id"] = folder_id

    print(json.dumps(output, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)


if __name__ == "__main__":
    main()
