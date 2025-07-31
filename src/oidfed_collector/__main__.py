from . import app

def main():
    """Run the app."""
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=12345)
    parser.add_argument("--log-level", type=str, default="info")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()