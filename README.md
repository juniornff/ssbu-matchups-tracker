# Smash Matchups Tracker

Web application to organize and manage **Super Smash Bros Ultimate** meetups and tournaments for local/small communities. It allows registering participants, characters, events, rounds, matches, and displaying their statistics.

## Features

- Participant management (registration, deactivation, reactivation).
- Complete SSBU character catalog.
- Event creation and attendance registration.
- Automatic round generation with Round Robin system.
- Match results recording (matchups) per round (best of 5).
- Detailed statistics: win rates by player, by character, and against opponents.
- Individual history for each participant.
- Current round configuration for quick access to ongoing matches.
- Automatic update of used characters based on played matches.
- Responsive interface (works on mobile).

## Technologies used

- **Backend**: Python + Flask
- **Database**: SQLite (with SQLAlchemy)
- **Frontend**: Bootstrap 5, Tom Select (for enhanced selects)
- **Task scheduling**: APScheduler

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- (Optional) Docker

## Local installation and execution

1. **Clone the repository**

    ```bash
    git clone https://github.com/tu-usuario/ssbu-league-manager.git
    cd ssbu-league-manager
    ```

2. **Create and activate a virtual environment (recommended)**

    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/Mac
    venv\Scripts\activate     # Windows
    ```
3. **Install dependencies**

    ```bash
    pip install -r requirements.txt
    ```

4. **Configure the secret code**

    Create a "pass.txt" file in the project root with a single line containing the password that will protect sensitive actions (e.g., deleting participants, events, etc.).

    ```bash
    echo "your_secret_password" > pass.txt
    ```

5. **Initialize the database**

    The application will automatically create the SQLite database at "instance/smash.db" and populate the characters on first start.

6. **Run the application**

    ```bash
    flask run --debug
    ```

    The app will be available at http://localhost:5000.

## Usage with Docker

If you prefer to use Docker for execution:

```bash
docker compose up -d
```

## License

This project is licensed under the MIT License. See the [LICENSE](https://raw.githubusercontent.com/juniornff/ssbu-matchups-tracker/refs/heads/main/LICENSE) file for more details.