# ==============================================================
#       |
#   \  ___  /                           _________
#  _  /   \  _    GÉANT                 |  * *  | Co-Funded by
#     | ~ |       Trust & Identity      | *   * | the European
#      \_/        Incubator             |__*_*__| Union
#       =
# ==============================================================

from . import app
from .config import CONFIG

def main():
    """Run the app."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=CONFIG.port, log_level=CONFIG.log_level)


if __name__ == "__main__":
    main()