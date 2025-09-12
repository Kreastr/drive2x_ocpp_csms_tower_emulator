set -e 
git pull
git submodule update --init --recursive
docker build -t py312d2x:latest -f Dockerfile-d2x drive2x-flow
docker build -t ocpp:latest . 
docker build -t vcp:latest -f Dockerfile-vcp .
docker-compose up -d

