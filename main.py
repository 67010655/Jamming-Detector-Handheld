import argparse
from detector import GPSJammerHandheld

def main():
    parser = argparse.ArgumentParser(description="GNSS Jamming Detector Handheld")
    parser.add_argument("--preview", action="store_true", help="Render UI preview to preview.png instead of using the LCD")
    args = parser.parse_args()

    app = GPSJammerHandheld(preview=args.preview)
    if args.preview:
        print("[INFO] Preview mode enabled. Output will be written to preview.png.")
    app.run()

if __name__ == "__main__":
    main()