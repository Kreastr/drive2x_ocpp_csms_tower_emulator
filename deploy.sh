set -e 
git pull
git submodule update --init --recursive
docker build -t ocpp:latest . 
docker build -t vcp:latest -f Dockerfile-vcp .
docker build -t proxy:latest -f Dockerfile-proxy .
docker-compose up -d

