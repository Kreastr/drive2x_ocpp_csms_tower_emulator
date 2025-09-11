set -e 
git pull
docker build -t ocpp:latest . 
docker build -t vcp:latest -f Dockerfile-vcp .
docker-compose up -d

