# Self-Hosted RStudio & JupyterLab Multi-User Platform

A private platform for managing individual RStudio and JupyterLab (Data Science Notebook) instances in a Linux Server.

## Core Features

- **User Self-Service:** Register, log in, and request personal RStudio or JupyterLab containers.
- **Admin Controls:**
  - Set resource quotas (memory, CPU, disk) per user.
  - Configure automatic session expiration (e.g., after 2 weeks).
- **Multi-Environment:** Users can launch either RStudio or JupyterLab (Jupyter Data Science Notebook) environments on demand.

---

## Technology Stack

- **Backend:** Python (FastAPI)
- **Frontend:** Jinja2 Templates
- **Authentication:** FastAPI-based sessions
- **Database:** SQLite (default), PostgreSQL (optional)
- **Containerization:** Docker (using `rocker/rstudio` and `jupyter/datascience-notebook` images)
- **Session Management:** Cron-based script or Celery
- **Reverse Proxy:** Nginx or Traefik

---

## User Workflow

1.  **Register/Login:** Users access the web portal.
2.  **Request Instance:** Users request an RStudio or JupyterLab instance from their dashboard.
3.  **Provisioning:** The server starts a new Docker container for the user.
    - Container details (ID, port, credentials/token, expiration) are stored in the database.
    - Example Docker commands:
      ```bash
      # RStudio
      docker run -d \
        --name rstudio-user-<username> \
        --memory="<quota>" \
        --cpus="<quota>" \
        -e PASSWORD=<generated_password> \
        -v /srv/rstudio-users/<username>:/home/rstudio \
        -p <host_port>:8787 \
        rocker/rstudio
      # JupyterLab
      docker run -d \
        --name jupyterlab-user-<username> \
        --memory="<quota>" \
        --cpus="<quota>" \
        -e JUPYTER_TOKEN=<generated_token> \
        -e JUPYTER_ENABLE_LAB=yes \
        -v /srv/jupyter-users/<username>:/home/jovyan/work \
        -p <host_port>:8888 \
        jupyter/datascience-notebook
      ```
4.  **Access Environment:** User accesses their instance via a unique URL (RStudio or JupyterLab, with credentials or token).

---

## Directory Structure

```
/opt/rstudio-portal/
├── app/                # FastAPI application code
├── templates/          # HTML templates
├── static/             # CSS, JavaScript files
├── docker_templates/   # Scripts for Docker container management
├── user_data/          # Persistent user-specific data
│   ├── <username1>/
│   └── <username2>/
└── db.sqlite3          # Database for user and instance metadata
```

---

## Deployment Overview

| Component          | Technology                  |
| ------------------ | --------------------------- |
| Web Portal         | FastAPI + Jinja2            |
| Auth & DB          | FastAPI + SQLite/PostgreSQL |
| RStudio Containers | Docker (`rocker/rstudio`)   |
| JupyterLab         | Docker (`jupyter/datascience-notebook`) |
| Resource Limits    | Docker options / XFS quotas |
| Expiration Control | Cron / Celery + Python      |
| Reverse Proxy      | Nginx / Traefik             |

---

## Deployment on a Linux (Ubuntu) Server

This guide outlines the steps to deploy the RStudio Portal on a Linux server, specifically targeting Ubuntu. Ensure you have `sudo` privileges for these operations.

**Prerequisites:**

1.  **Ubuntu Server:** A running Ubuntu server instance (e.g., version 20.04 LTS or newer).
2.  **Docker:** Docker CE installed. Follow the official Docker installation guide for Ubuntu: [https://docs.docker.com/engine/install/ubuntu/](https://docs.docker.com/engine/install/ubuntu/)
3.  **Nginx:** Nginx web server installed. `sudo apt update && sudo apt install nginx`
4.  **Miniconda/Anaconda:** For managing the Python environment. Download and install from [https://docs.conda.io/projects/miniconda/en/latest/](https://docs.conda.io/projects/miniconda/en/latest/) or [https://www.anaconda.com/products/distribution](https://www.anaconda.com/products/distribution).
5.  **Git:** For cloning the repository. `sudo apt install git`

**Deployment Steps:**

1.  **Clone the Repository:**

    ```bash
    git clone git@github.com:CSI-Genomics-and-Data-Analytics-Core/rstudio-portal.git /opt/rstudio-portal
    cd /opt/rstudio-portal
    ```

2.  **Set up Python Environment:**

    - Create and activate a Conda environment:
      ```bash
      conda create --name rstudio-env python=3.9 -y
      conda activate rstudio-env
      ```
    - Install Python dependencies:
      ```bash
      pip install -r requirements.txt
      ```

3.  **Initialize Database & Directories:**

    - The FastAPI application will create `db.sqlite3` and the `user_data` directory on its first run if they don't exist. Ensure the directory `/opt/rstudio-portal` is writable by the user running the FastAPI application, or adjust paths in `app/main.py` (`BASE_DIR`, `USER_DATA_BASE_DIR`) and create them manually with appropriate permissions.
    - Manually create the base directory for user data if needed:
      ```bash
      sudo mkdir -p /opt/rstudio-portal/user_data
      sudo chown <your_app_user>:<your_app_group> /opt/rstudio-portal/user_data
      # Replace <your_app_user> and <your_app_group> with the user/group that will run the FastAPI app
      ```

4.  **Configure Nginx:**

    - Copy the provided `nginx.conf` to Nginx's configuration directory. It's recommended to place it in `sites-available` and create a symbolic link to `sites-enabled`.
      ```bash
      sudo cp nginx.conf /etc/nginx/sites-available/rstudio-portal.conf
      sudo ln -s /etc/nginx/sites-available/rstudio-portal.conf /etc/nginx/sites-enabled/
      ```
    - **Important:** Edit `/etc/nginx/sites-available/rstudio-portal.conf`:
      - Update `server_name` if you have a domain, or leave as `_` for IP-based access.
      - Ensure the `alias` path in the `location /static` block points to the correct static files directory (e.g., `/opt/rstudio-portal/static`).
      - If you changed the FastAPI application port from `8000`, update the `upstream fastapi_app` block.
    - Test Nginx configuration and reload:
      ```bash
      sudo nginx -t
      sudo systemctl reload nginx
      ```

5.  **Run the FastAPI Application:**

    - It's highly recommended to run the FastAPI application using a process manager like `systemd` or `supervisor` for production.

    - **Using `systemd` (Recommended):**

      1.  Create a systemd service file at `/etc/systemd/system/rstudio-portal.service`:

          ```ini
          [Unit]
          Description=RStudio Portal FastAPI Application
          After=network.target docker.service
          Requires=docker.service

          [Service]
          User=<your_app_user> # User that owns /opt/rstudio-portal and has Docker permissions
          Group=<your_app_group>
          WorkingDirectory=/opt/rstudio-portal
          Environment="PATH=<path_to_your_conda_installation>/envs/<your_conda_env_name>/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" # Adjust Conda path and env name
          ExecStart=<path_to_your_conda_installation>/envs/<your_conda_env_name>/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 # Adjust Conda path, env name, and port
          Restart=always
          RestartSec=3

          [Install]
          WantedBy=multi-user.target
          ```

          - **Note:** Replace `<your_app_user>` and `<your_app_group>`. This user needs to be able to run Docker commands (usually by being part of the `docker` group: `sudo usermod -aG docker <your_app_user>`).
          - Adjust `Environment="PATH=..."` and `ExecStart` to match your Conda installation path (e.g., `/opt/miniconda3`, `/home/<your_user>/anaconda3`, etc.) and environment name.

      2.  Reload systemd, enable, and start the service:
          ```bash
          sudo systemctl daemon-reload
          sudo systemctl enable rstudio-portal.service
          sudo systemctl start rstudio-portal.service
          sudo systemctl status rstudio-portal.service # To check status
          ```

    - **Directly (for testing, not recommended for production):**
      ```bash
      conda activate rstudio-env
      cd /opt/rstudio-portal
      uvicorn app.main:app --host 0.0.0.0 --port 8000
      ```

6.  **Access the Portal:**

    - Open your web browser and navigate to `http://<your_server_ip_or_domain>`.

### Docker Deployment

This section details how to build and run the RStudio Portal application itself as a Docker container. This is separate from the RStudio containers the application will manage.

**1. Build the Docker Image:**

Navigate to the root directory of the project (where the `Dockerfile` is located) and run:

```bash
_DOCKER_BUILDKIT=1 docker build -t rstudio-portal-app .
```

**2. Run the Docker Container:**

The application is configured using environment variables. When running the Docker container, you need to pass these variables and mount volumes for persistent data (database and user RStudio data).

**Example `docker run` command:**

```bash
docker run -d --name rstudio-portal-app-container \
  -p 8000:8000 \
  -v /path/on/host/for/db_data:/mnt/db_data \
  -v /path/on/host/for/user_data:/mnt/user_data \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DB_MOUNT_PATH="/mnt/db_data" \
  -e DATABASE_FILENAME="rstudio_portal.db" \
  -e USER_DATA_MOUNT_PATH="/mnt/user_data" \
  -e INITIAL_ADMIN_USERNAME="admin" \
  -e RSTUDIO_IMAGE="rocker/rstudio:latest" \
  -e RSTUDIO_MIN_PORT="8787" \
  -e RSTUDIO_MAX_PORT="9000" \
  -e RSTUDIO_DEFAULT_MEMORY="1g" \
  -e RSTUDIO_DEFAULT_CPUS="1.0" \
  -e RSTUDIO_SESSION_EXPIRY_DAYS="14" \
  -e SESSION_SECRET_KEY="your_very_strong_and_random_secret_key_here" \\ # pragma: allowlist secret
  -e UVICORN_HOST="0.0.0.0" \
  -e UVICORN_PORT="8000" \
  rstudio-portal-app
```

**Explanation of `docker run` options:**

- `-d`: Run the container in detached mode (in the background).
- `--name rstudio-portal-app-container`: Assign a name to the container for easier management.
- `-p 8000:8000`: Map port 8000 of the host to port 8000 of the container (where Uvicorn runs by default, or as configured by `UVICORN_PORT`).
- `-v /path/on/host/for/db_data:/mnt/db_data`: Mount a host directory into the container at `/mnt/db_data`. This is where the application will store its database. **Replace `/path/on/host/for/db_data` with an actual absolute path on your Docker host.**
- `-v /path/on/host/for/user_data:/mnt/user_data`: Mount a host directory into the container at `/mnt/user_data`. This is where the application will store RStudio user-specific data. **Replace `/path/on/host/for/user_data` with an actual absolute path on your Docker host.**
- `-v /var/run/docker.sock:/var/run/docker.sock`: **Crucial for managing RStudio containers.** This mounts the Docker socket from the host into the container, allowing the FastAPI application to start, stop, and manage other Docker containers (the RStudio instances).
- `-e VARIABLE_NAME="value"`: Set environment variables required by the application (see `.env.example` for a full list).
  - `DB_MOUNT_PATH`: Should match the target path of the database volume mount inside the container (e.g., `/mnt/db_data`).
  - `DATABASE_FILENAME`: The name of the SQLite database file.
  - `USER_DATA_MOUNT_PATH`: Should match the target path of the user data volume mount inside the container (e.g., `/mnt/user_data`).
  - `SESSION_SECRET_KEY`: **MUST be set to a strong, random string for security.**
- `rstudio-portal-app`: The name of the Docker image built in the previous step.

**Important Considerations for Docker Deployment:**

- **Docker Socket Permissions:** The user inside the container (`appuser`) needs permission to access the Docker socket. If you encounter permission issues, you might need to adjust the group ownership or permissions of `/var/run/docker.sock` on the host, or run the container with a user that has appropriate rights (though running as root is generally discouraged for the application itself).
- **Persistent Storage:** Ensure the host paths used for volumes (`/path/on/host/for/db_data`, `/path/on/host/for/user_data`) exist and have correct permissions for the Docker daemon to write to them.
- **Environment Variables:** Always provide all required environment variables. Refer to `.env.example` for the complete list and their purpose.
- **Nginx for Docker:** If you are running the FastAPI app in Docker and still want to use Nginx as a reverse proxy (e.g., for SSL termination, serving static files directly, or routing to multiple applications), Nginx would typically run on the host or as another Docker container. The Nginx configuration would then proxy requests to the Dockerized FastAPI application (e.g., `proxy_pass http://localhost:8000;` if port 8000 is mapped to the host).

---

## Next Steps & Future Enhancements

- Admin dashboard for user and instance management.
- Integration with LDAP or OAuth for authentication.
- Automated credential generation and secure storage.
- Resource usage monitoring (RAM, CPU, disk).
- Option for users to download their home directory as a ZIP file.
- **Support for additional environments (e.g., VS Code, R Shiny) in the future.**
