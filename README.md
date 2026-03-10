# Smash Matchups Tracker

Web application to organize and manage **Super Smash Bros Ultimate** meetups and tournaments for local/small communities. It allows registering participants, characters, events, rounds, matches, tournaments and displaying their statistics.

## Features

- Participant management (registration, deactivation, reactivation).
- Complete SSBU character catalog. (images used come from [spriters-resource](https://www.spriters-resource.com/nintendo_switch/supersmashbrosultimate/))
- Event creation and attendance registration.
- Automatic round generation with Round Robin system.
- Match results recording (matchups) per round (best of 5).
- Tournament Brackets Engine by Integrating the [Drarig29/brackets-manager.js](https://github.com/Drarig29/brackets-manager.js) library through a [custom-built REST API](https://github.com/juniornff/brackets-manager-server).
- Detailed statistics: win rates by player, by character, and against opponents.
- Individual history for each participant.
- Current round configuration for quick access to ongoing matches.
- Automatic update of used characters based on played matches.
- Responsive interface (works on mobile).
- Automated deployment via GitHub Actions (CI/CD) to a private server.

## Technologies used

- **Backend**: Python + Flask
- **Database**: SQLite (with SQLAlchemy)
- **Frontend**: Bootstrap 5, Tom Select (for enhanced selects)
- **Task scheduling**: APScheduler
- **APIs Used**: [Custom-built REST API](https://github.com/juniornff/brackets-manager-server) for the [Drarig29/brackets-manager.js](https://github.com/Drarig29/brackets-manager.js) library
- **CI/CD**: GitHub Actions, Docker, GitHub Container Registry (ghcr.io)

## Future Plans

- **MySQL Database Integration:** Enable the option to use MySQL as a database alternative to SQLite.
- **User Authentication & Profiles:** Implement a secure user login system (e.g., OAuth or email/password) to enable personalized experiences, role‑based access control, and the ability for players to manage their registrations and match histories.

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Node.js (for the API server)
- (Optional) Docker

## Usage with Docker

1. **Prepare the project directory**

    Create a folder for the project and navigate into it:

    ```bash
    mkdir ssbu-matchups && cd ssbu-matchups
    ```

2. **Create the `docker-compose.yml` file**

    Copy the following content into a file named `docker-compose.yml` or [download it](docker-compose.yml):

    ```yaml
    services:
    tournament-server:
        image: ghcr.io/juniornff/brackets-manager-server:latest
        container_name: brackets-manager-api
        restart: unless-stopped
        ports:
        - "3000:3000"
        volumes:
        - ./data:/app/data
        environment:
        - DATA_FILE=data/db.json
        networks:
        - smash-net

    ssbu_matchups:
        image: ghcr.io/juniornff/ssbu-matchups-tracker:latest
        container_name: Ssbu_Matchups
        restart: unless-stopped
        ports:
        - "5000:5000"
        volumes:
        - ./instance:/app/instance
        environment:
        - API_TORNEOS_URL=http://tournament-server:3000
        - SECRET_KEY=${SECRET_KEY}
        - SECRET_CODE=${SECRET_CODE}
        depends_on:
        - tournament-server
        networks:
        - smash-net

    networks:
    smash-net:
        driver: bridge
    ```

3. **Configure environment variables (optional but recommended)**

    The application uses two important secret values:
    - `SECRET_KEY`: Used by Flask for session security and cryptographic signing.
    - `SECRET_CODE`: A custom secret that protects sensitive actions (e.g., deleting events, participants, etc.).

    You can define these variables in a `.env` file placed in the same directory as your `docker-compose.yml`.  
    Create a file named `.env` with the following content (replace the values with your own strong secrets):

    ```bash
    SECRET_KEY=your_flask_secret_key_here
    SECRET_CODE=your_custom_secret_code_here
    ```

    If you do not provide these variables, the application will automatically generate random values on startup and log them for reference.
    For production, it is strongly recommended to set them explicitly to maintain session persistence and avoid unexpected changes.

4. **Start the containers**

    Run the following command to pull the images and start the services in the background:

    ```bash
    docker compose up -d
    ```

    Docker Compose will automatically create the required networks and volumes. The `tournament-server` API will be available at `http://localhost:3000` and the main application at `http://localhost:5000`.

5. **Verify the services are running**

    Check the container status:

    ```bash
    docker compose ps
    ```

    You should see both containers with `Up` status. To view the logs:

    ```bash
    docker compose logs -f
    ```

    Press `Ctrl+C` to exit the log view.

6. **Access the application**

    Open your browser and go to `http://localhost:5000`. You should see the Smash Matchups Tracker homepage.

7. **Stopping and removing the containers**

    To stop the services without deleting data:

    ```bash
    docker compose stop
    ```

    To stop and remove containers, networks, and any created volumes (your data in `./data` and `./instance` will persist because they are bind mounts):

    ```bash
    docker compose down
    ```

8. **Updating to the latest version**

    The images are automatically rebuilt and published on GitHub Container Registry whenever changes are pushed to the `main` branch. To update your local containers to the latest version:

    ```bash
    docker compose pull
    docker compose up -d
    ```

    This will pull fresh images and recreate the containers.

## Local installation and execution

If you prefer to run the application directly on your system without Docker, follow these steps.

1. **Clone the repository**

    ```bash
    git clone https://github.com/juniornff/ssbu-matchups-tracker.git
    cd ssbu-matchups-tracker
    ```

2. **Clone and start the API repository**

    ```bash
    git clone https://github.com/juniornff/brackets-manager-server.git
    cd brackets-manager-server
    npm install
    npm start
    ```

3. **Create and activate a virtual environment (recommended)**

    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/Mac
    venv\Scripts\activate     # Windows
    ```
4. **Install dependencies**

    ```bash
    pip install -r requirements.txt
    ```

5. **Configure environment variables**

    The application requires the following environment variables:

    - `SECRET_KEY`: Used by Flask for session security and cryptographic signing.
    - `SECRET_CODE`: A custom secret that protects sensitive actions (e.g., deleting events, participants, etc.).
    - `API_TORNEOS_URL`: URL of the tournament manager API (default is `http://localhost:3000` if not set).

    You can set these variables in your terminal before running the application, or use a `.env` file with a tool like `python-dotenv` (the application does not load `.env` automatically in development mode; you need to export them manually or use a package like `python-dotenv` in your own setup).

    **On Linux / Mac:**
    ```bash
    export SECRET_KEY="your_flask_secret_key"
    export SECRET_CODE="your_custom_secret_code"
    export API_TORNEOS_URL="http://localhost:3000"  # adjust if your API runs elsewhere
    ```

    **On Windows:**
    ```bash
    # Command Prompt
    set SECRET_KEY=your_flask_secret_key
    set SECRET_CODE=your_custom_secret_code
    set API_TORNEOS_URL=http://localhost:3000
    # PowerShell
    $env:SECRET_KEY="your_flask_secret_key"
    $env:SECRET_CODE="your_custom_secret_code"
    $env:API_TORNEOS_URL="http://localhost:3000"
    ```
    If you do not provide these variables, the application will automatically generate random values on startup and log them for reference.
    For production, it is strongly recommended to set them explicitly to maintain session persistence and avoid unexpected changes.

6. **Initialize the database**

    The application will automatically create the SQLite database at "instance/smash.db" and populate the characters on first start.

6. **Run the application**

    ```bash
    flask run --debug
    ```

    The app will be available at http://localhost:5000.

## License

This project is licensed under the MIT License. See the [LICENSE](https://raw.githubusercontent.com/juniornff/ssbu-matchups-tracker/refs/heads/main/LICENSE) file for more details.