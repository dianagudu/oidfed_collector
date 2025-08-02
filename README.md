# oidfed-collector: The OpenID Federation Entity Collection Service

This project implements the [OpenID Federation Entity Collection specification](https://zachmann.github.io/openid-federation-entity-collection/main.html).

## Installation

To install the oidfed-collector, you can use pip or Docker.

### Using pip

```bash
pip install oidfed_collector
```

### Using Docker

```bash
docker pull ddgu/oidfed-collector:latest
```

## Configuration

The service accepts a configuration file in JSON format. You can specify the configuration file using the `CONFIG` environment variable. By default, it looks for `config.json` in the current directory.
The repository includes an example configuration file `config.json`. You can modify it according to your needs. Here is an example configuration with the default values:

```json
{
    "port": 12345,
    "log_level": "info",
    "api_base_url": "/collection",
    "cache": {
        "ttl": 300,
        "max_size": 1000,
        "cleanup_interval": 60
    },
    "session": {
        "max_concurrent_requests": 100,
        "ttl": 30
    }
}
```

- The `port` specifies the port on which the service will run.
- The `log_level` can be set to `debug`, `info`, `warning`, `error`, or `critical`.
- The `api_base_url` is the base URL for the API endpoints.
- The `cache` section configures the caching behavior, including time-to-live (`ttl`), maximum size in items, and cleanup interval.
- The `session` section configures HTTP session management, including maximum concurrent requests and session time-to-live (`ttl`).

## Running the Service

To run the service, you can run it directly as a Python module or from a Docker container.

### Using Python

```bash
python -m oidfed_collector
```

### Using Docker

```bash
docker run -d -p 12345:12345 -v $(pwd)/config.json:/app/config.json ddgu/oidfed-collector:latest
```

We also provide a `docker-compose.yaml` file for easier deployment, which mounts the configuration file from the current directory. Modify to your needs and use it as follows:

```bash
docker-compose up -d
```

## Usage

Once the service is running, you can access the API at `http://localhost:12345/collection`. The service supports a single endpoint for entity collection as defined in the OpenID Federation Entity Collection specification.

## Development

To contribute to the development of oidfed-collector, you can clone the repository and install the dependencies using poetry:

```bash
git clone https://github.com/dianagudu/oidfed-collector.git
cd oidfed-collector
poetry install
```

You can then run the service locally:

```bash
poetry run oidfed-collector
```

If you wish to build the Docker image locally, note that we provide a multi-stage Dockerfile, with separate targets for development and production. You can build it with:

```bash
docker build --target development -t oidfed-collector:dev .
docker build --target production -t oidfed-collector:latest .
```

## License

This project is licensed under the MIT License.

This project includes code from fedservice (https://github.com/SUNET/fedservice), licensed under the Apache License, Version 2.0.
Modifications were made to adapt it for this project.
