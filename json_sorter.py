import json
from argparse import ArgumentParser

argp = ArgumentParser(description="Simple json list sorter for OCPP dumps")
argp.add_argument("input_filename")
argp.add_argument("output_filename")

args = argp.parse_args()

with open(args.input_filename) as f:
    datain = json.load(f)

def ocpp_key(record):
    cmpnt = record["component"]["name"]
    var = record["variable"]["name"]
    return f"{cmpnt}-{var}"

data_out = sorted(datain, key=ocpp_key)

with open(args.output_filename, "w") as f:
    json.dump(data_out, f)