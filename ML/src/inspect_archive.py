from pathlib import Path
from zipfile import ZipFile


archive_dir = Path("data/external/firms_archives")
zip_files = list(archive_dir.glob("*.zip"))

if not zip_files:
    raise FileNotFoundError("No ZIP file found in data/external/firms_archive")

archive_file = max(zip_files, key=lambda file: file.stat().st_mtime)

print(f"Archive: {archive_file.name}")
print(f"ZIP size: {archive_file.stat().st_size / 1024 / 1024:.2f} MB")

with ZipFile(archive_file) as archive:
    print("\nFiles inside ZIP:")

    for info in archive.infolist():
        size_mb = info.file_size / 1024 / 1024
        print(f"  - {info.filename} ({size_mb:.2f} MB)")

    csv_files = [
        info.filename
        for info in archive.infolist()
        if info.filename.lower().endswith(".csv")
    ]

    if csv_files:
        csv_file = csv_files[0]

        print(f"\nCSV selected: {csv_file}")
        print("\nFirst two lines:")

        with archive.open(csv_file) as file:
            print(file.readline().decode("utf-8-sig").strip())
            print(file.readline().decode("utf-8-sig").strip())