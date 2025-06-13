# GeDaC Data Science Portal: Self-Hosted RStudio & JupyterLab

A private, multi-user platform for managing individual RStudio and JupyterLab (Data Science Notebook) instances on a Linux Server.

![Architecture Diagram](architecture.png)

The platform uses Docker containers to isolate user environments, a FastAPI backend for user management, and a reverse proxy to route traffic to the appropriate instances.

## Core Features

- **User Self-Service:** Register, log in, and request personal RStudio or JupyterLab containerized environments.
- **Admin Controls:**
  - Manage users and instances.
  - Configure resource quotas (memory, CPU) per instance.
  - Set automatic session expiration.
- **Multi-Environment Support:** Launch either RStudio or JupyterLab instances on demand.
- **Persistent Storage:** User data is saved in dedicated volumes.

---

## Technology Stack

- **Backend:** Python (FastAPI)
- **Frontend:** Jinja2 Templates with HTML & CSS
- **Authentication:** Secure session-based authentication.
- **Database:** SQLite (default).
- **Containerization:** Docker (utilizing `rocker/rstudio` and `jupyter/datascience-notebook` base images).
- **Instance Lifecycle Management:** Python scripts (e.g., for cleanup of expired instances).
- **Reverse Proxy (Recommended):** Nginx or Traefik for SSL termination and routing.
---

## User Workflow

1.  **Access Portal:** Users navigate to the web portal.
2.  **Register/Login:** New users register; existing users log in.
3.  **Request Environment:** From their dashboard, users can request an RStudio or a JupyterLab instance.
4.  **Provisioning:**
    - The backend initiates the creation of a new Docker container for the user.
    - Container details (ID, assigned port, access credentials/token, expiration date) are recorded in the database.
    - Example Docker launch commands (managed by the application):
      ```bash
      # RStudio Instance
      docker run -d \
        --name rstudio-<user_identifier>-<unique_id> \
        --memory="<memory_limit>" \
        --cpus="<cpu_limit>" \
        -e PASSWORD=<generated_password> \
        -v /path/to/user_data/<user_identifier>:/home/rstudio \
        -p <assigned_host_port>:8787 \
        <RSTUDIO_DOCKER_IMAGE>

      # JupyterLab Instance
      docker run -d \
        --name jupyterlab-<user_identifier>-<unique_id> \
        --memory="<memory_limit>" \
        --cpus="<cpu_limit>" \
        -e JUPYTER_TOKEN=<generated_token> \
        -e JUPYTER_ENABLE_LAB=yes \
        -v /path/to/user_data/<user_identifier>:/home/jovyan/work \
        -p <assigned_host_port>:8888 \
        <JUPYTER_DOCKER_IMAGE>
      ```
5.  **Access Instance:** Users receive a unique link and credentials/token to access their running RStudio or JupyterLab environment.

---

## Project Structure

```
/rstudio-portal/
├── app/                    # FastAPI application source code
│   ├── __init__.py
│   ├── main.py             # Main application logic, request handling
│   ├── core/               # Core components (e.g., configuration)
│   │   └── config.py
│   ├── db/                 # Database interaction logic
│   │   └── database.py
│   ├── auth/               # Authentication logic
│   │   └── security.py
│   └── routers/            # (Future) API route definitions
├── templates/              # Jinja2 HTML templates for the frontend
├── static/                 # Static assets (CSS, JavaScript, images)
├── docker_templates/       # Helper scripts for Docker (e.g., cleanup)
├── user_data/              # Root directory for persistent user-specific data volumes
│   ├── <username_part1>/
│   └── <username_part2>/
├── .env.example            # Example environment variable configuration
├── Dockerfile              # For building the application's Docker image
├── requirements.txt        # Python dependencies
├── nginx.conf              # Example Nginx configuration
└── README.md               # This file
```
The `db.sqlite3` database file will be created (by default in the project root, or as specified by `DB_MOUNT_PATH` and `DATABASE_FILENAME` environment variables).

---
## Deployment on a Linux (Ubuntu) Server

This guide outlines deploying the GeDaC Data Science Portal on a Linux server (Ubuntu focused). `sudo` privileges are required.

**Prerequisites:**

1.  **Ubuntu Server:** Version 20.04 LTS or newer recommended.
2.  **Docker Engine:** Install Docker CE. Follow the [official Docker installation guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
3.  **Nginx (Recommended):** For reverse proxy. Install using `sudo apt update && sudo apt install nginx`.
4.  **Python Environment Manager (Miniconda/Anaconda):** For managing the application's Python environment.
    - Miniconda: [https://docs.conda.io/projects/miniconda/en/latest/](https://docs.conda.io/projects/miniconda/en/latest/)
    - Anaconda: [https://www.anaconda.com/products/distribution](https://www.anaconda.com/products/distribution)
5.  **Git:** For cloning the repository. `sudo apt install git`.

**Deployment Steps:**

1.  **Clone Repository:**
    ```bash
    sudo git clone git@github.com:CSI-Genomics-and-Data-Analytics-Core/rstudio-portal.git /opt/rstudio-portal
    cd /opt/rstudio-portal
    ```
    *(Using `/opt/rstudio-portal` as the application directory. Adjust if needed.)*

2.  **Set Up Python Environment:**
    ```bash
    # Create a Conda environment (e.g., named 'dspenv' for Data Science Portal)
    conda create --name dspenv python=3.9 -y
    conda activate dspenv

    # Install dependencies
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables:**
    - Copy the example environment file:
      ```bash
      cp .env.example .env
      ```
    - **Edit `.env` and set appropriate values.** Refer to the "Configuration" section below and comments in `.env.example` for details on each variable. Key variables include:
        - `SESSION_SECRET_KEY` (set to a strong random string)
        - `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`
        - `DB_MOUNT_PATH` and `DATABASE_FILENAME` (if not using the default location)
        - `USER_DATA_MOUNT_PATH` (if not using the default `user_data` subdirectory)
        - Docker image names and resource limits if defaults are not suitable.

4.  **Initialize Directories & Permissions:**
    - The application attempts to create the database and `user_data` directory if they don't exist, based on configured paths.
    - If `USER_DATA_MOUNT_PATH` or `DB_MOUNT_PATH` point to custom locations, ensure these directories exist and are writable by the user running the FastAPI application.
      ```bash
      # Example: If USER_DATA_MOUNT_PATH=/srv/portal_user_data
      sudo mkdir -p /srv/portal_user_data
      sudo chown <your_app_user>:<your_app_group> /srv/portal_user_data

      # Example: If DB_MOUNT_PATH=/var/portal_db
      sudo mkdir -p /var/portal_db
      sudo chown <your_app_user>:<your_app_group> /var/portal_db
      ```
      Replace `<your_app_user>` and `<your_app_group>` with the actual user/group.

5.  **Configure Nginx (Reverse Proxy - Recommended):**
    - Copy the example Nginx configuration:
      ```bash
      sudo cp nginx.conf /etc/nginx/sites-available/datascience-portal.conf
      sudo ln -s /etc/nginx/sites-available/datascience-portal.conf /etc/nginx/sites-enabled/
      ```
    - **Edit `/etc/nginx/sites-available/datascience-portal.conf`:**
        - Update `server_name your_domain.com www.your_domain.com;` to your server's domain or IP address.
        - Verify the `root` path in `location /static` correctly points to `/opt/rstudio-portal/static` (or your chosen application directory + `/static`).
        - Ensure `proxy_pass http://127.0.0.1:8001;` matches the host and port Uvicorn will run on (defined by `UVICORN_HOST`, `UVICORN_PORT` in your `.env` or defaults).
    - Test and reload Nginx:
      ```bash
      sudo nginx -t
      sudo systemctl reload nginx
      ```

6.  **Run the FastAPI Application:**
    For production, use a process manager like `systemd`.

    - **Using `systemd`:**
      1.  Create `/etc/systemd/system/datascience-portal.service`:
          ```ini
          [Unit]
          Description=GeDaC Data Science Portal FastAPI Application
          After=network.target docker.service
          Requires=docker.service

          [Service]
          User=<your_app_user>
          Group=<your_app_group>
          WorkingDirectory=/opt/rstudio-portal # Or your chosen application directory

          # Option 1: Load environment variables from .env file
          EnvironmentFile=/opt/rstudio-portal/.env

          # Option 2: Define all environment variables directly (less common for many vars)
          # Environment="SESSION_SECRET_KEY=your_secret"
          # Environment="DB_MOUNT_PATH=/var/portal_db"
          # ... etc.

          # Ensure Conda environment's bin directory is in PATH
          Environment="PATH=/opt/miniconda3/envs/dspenv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" # ADJUST Conda path & env name
          ExecStart=/opt/miniconda3/envs/dspenv/bin/python app/main.py # ADJUST Conda path & env name. Runs the __main__ block in main.py

          Restart=always
          RestartSec=5

          [Install]
          WantedBy=multi-user.target
          ```
          - Replace `<your_app_user>`, `<your_app_group>`. This user must have permissions to run Docker commands (add to `docker` group: `sudo usermod -aG docker <your_app_user>`).
          - **Adjust `EnvironmentFile` path if your `.env` file is elsewhere.**
          - **Crucially, adjust `Environment="PATH=..."` and `ExecStart`** to your Conda installation path (e.g., `/opt/miniconda3`, `/home/user/anaconda3`) and your Conda environment name (e.g., `dspenv`).
          - The `ExecStart` now directly calls `python app/main.py`, which will use the Uvicorn server settings from `app.core.config` (sourced from `.env`).

      2.  Reload systemd, enable, and start:
          ```bash
          sudo systemctl daemon-reload
          sudo systemctl enable datascience-portal.service
          sudo systemctl start datascience-portal.service
          sudo systemctl status datascience-portal.service # Check status
          journalctl -u datascience-portal.service -f # View logs
          ```

    - **Directly (for Development/Testing Only):**
      ```bash
      conda activate dspenv
      cd /opt/rstudio-portal # Or your chosen application directory
      # Ensure .env file is present in this directory or variables are exported
      python app/main.py
      ```
      The application will start using Uvicorn settings defined in `app.core.config` (via `.env` or defaults).

7.  **Access the Portal:**
    Navigate to `http://<your_server_ip_or_domain>`.

---

## Configuration (Environment Variables)

The application is configured using environment variables. These can be set in a `.env` file in the project root or directly in the environment where the application runs. See `.env.example` for a comprehensive list.

**Key Variables:**

*   `SESSION_SECRET_KEY`: **Critical for security.** A long, random string used to sign session cookies. Generate one using `openssl rand -hex 32`.
*   `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`: Credentials for the first admin user, created on initial database setup.
*   `DB_MOUNT_PATH`: Absolute path to the directory where the SQLite database file will be stored. If empty, defaults to the project root.
*   `DATABASE_FILENAME`: Name of the SQLite database file (e.g., `portal.db`). Defaults to `db.sqlite3`.
*   `USER_DATA_MOUNT_PATH`: Absolute path to the base directory for storing persistent user data volumes. If empty, defaults to a `user_data` subdirectory within the project.
*   `RSTUDIO_DOCKER_IMAGE`, `JUPYTER_DOCKER_IMAGE`: Specify the Docker images to use for RStudio and JupyterLab instances.
*   `RSTUDIO_MIN_PORT`, `RSTUDIO_MAX_PORT`, `JUPYTER_MIN_PORT`, `JUPYTER_MAX_PORT`: Port ranges on the host for mapping to container services.
*   `RSTUDIO_DEFAULT_MEMORY`, `RSTUDIO_DEFAULT_CPUS`, `JUPYTER_DEFAULT_MEMORY`, `JUPYTER_DEFAULT_CPUS`: Default resource limits for new instances.
*   `RSTUDIO_SESSION_EXPIRY_DAYS`, `JUPYTER_SESSION_EXPIRY_DAYS`: How long instances remain active before automatic cleanup.
*   `UVICORN_HOST`, `UVICORN_PORT`: Host and port for the Uvicorn server running the FastAPI application.

---
## Docker Deployment (Application Container)

This section describes running the **GeDaC Data Science Portal application itself** as a Docker container. This is distinct from the RStudio/JupyterLab instances it manages.

**1. Build the Application Docker Image:**
   From the project root (containing the `Dockerfile`):
   ```bash
   docker build -t datascience-portal-app .
   ```

**2. Run the Application Container:**
   You'll need to pass environment variables and mount volumes for the database, user data, and the Docker socket.

   **Example `docker run` command:**
   ```bash
   docker run -d --name ds-portal-container \
     -p 8001:8001 \ # Map host port to Uvicorn port inside container
     -v /path/on/host/for_portal_db:/app/database_mount \      # Database storage
     -v /path/on/host/for_portal_user_data:/app/user_data_mount \ # User instance data
     -v /var/run/docker.sock:/var/run/docker.sock \          # Docker socket access
     -e SESSION_SECRET_KEY='your_very_strong_random_secret_key' \ # pragma: allowlist secret
     -e INITIAL_ADMIN_USERNAME='admin' \
     -e INITIAL_ADMIN_PASSWORD='securepassword' \ # pragma: allowlist secret
     -e DB_MOUNT_PATH='/app/database_mount' \
     -e DATABASE_FILENAME='portal_main.db' \
     -e USER_DATA_MOUNT_PATH='/app/user_data_mount' \
     # Add all other necessary RStudio/JupyterLab config env vars from .env.example
     -e RSTUDIO_DOCKER_IMAGE='rocker/rstudio:latest' \
     -e JUPYTER_DOCKER_IMAGE='jupyter/datascience-notebook:latest' \
     # ... (other env vars like ports, memory, expiry, etc.)
     -e UVICORN_HOST='0.0.0.0' \
     -e UVICORN_PORT='8001' \
     datascience-portal-app
   ```

   **Key `docker run` options explained:**
   - `-p 8001:8001`: Maps host port 8001 to container port 8001 (or as set by `UVICORN_PORT`).
   - `-v /path/on/host/for_portal_db:/app/database_mount`: Mounts a host directory for the database.
     - `DB_MOUNT_PATH` inside the container must then be `/app/database_mount`.
   - `-v /path/on/host/for_portal_user_data:/app/user_data_mount`: Mounts a host directory for user instance data.
     - `USER_DATA_MOUNT_PATH` inside the container must then be `/app/user_data_mount`.
   - `-v /var/run/docker.sock:/var/run/docker.sock`: **Essential.** Allows the application container to manage other Docker containers.
   - `-e VARIABLE="value"`: Set all required environment variables. **Crucially, `DB_MOUNT_PATH` and `USER_DATA_MOUNT_PATH` must match the *target paths* of your volume mounts inside the container.**

   **Important Considerations for Dockerized Application:**
   - **Permissions:** The user inside the application container (defined in `Dockerfile`, often non-root) needs access to the mounted Docker socket and write permissions to the mounted data/db volumes.
   - **Host Paths:** Replace `/path/on/host/...` with actual, absolute paths on your Docker host. These directories must exist.
   - **Nginx with Dockerized App:** If using Nginx as a reverse proxy, it would run on the host (or as another container) and proxy requests to the mapped port of the `ds-portal-container` (e.g., `proxy_pass http://localhost:8001;`).

---

## Future Enhancements

- Comprehensive admin dashboard for user and instance lifecycle management.
- Integration with institutional authentication (LDAP, OAuth2/OIDC).
- Enhanced resource usage monitoring and reporting.
- User self-service for data backup/download.
- Support for additional development environments (e.g., VS Code Server, R Shiny Apps).
- More granular permission controls.
