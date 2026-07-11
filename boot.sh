#!/usr/bin/env bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git
rm -rf /opt/advent
git clone https://github.com/vnrbchnk-lang/AI-advent-challenge.git /opt/advent
sed -i 's/\r$//' /opt/advent/week6/deploy/*.sh /opt/advent/week6/deploy/nginx.conf
bash /opt/advent/week6/deploy/install.sh
