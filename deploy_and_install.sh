#!/bin/sh

set -eu

LINE="-------------------------------------------------------------------"
DEST_IP=""
DEST_UN="pi"
REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MEDIAMTX_DIR="$REPO_DIR/pi_camera/mtx"
MODEL_DIR="$REPO_DIR/pi_camera/models"
SCRIPTS_DIR="$REPO_DIR/pi_camera/scripts"
SERVICES_DIR="$REPO_DIR/pi_camera/services"
KEY_NAME="$HOME/.ssh/id_rsa_pi"

usage() {
    echo "$LINE"
    echo "Deploy and install script for Raspberry Pi ATR"
    echo "Usage: $0 -i <IP or host of destination Pi>"
    echo "$LINE"
    exit 1
}

error() {
    echo "Error: $*" >&2
    exit 1
}

scp_to_remote() {
    scp -i "$KEY_NAME" -r "$1" "$DEST_UN@$DEST_IP:$2"
}

ssh_remote() {
    ssh -i "$KEY_NAME" "$DEST_UN@$DEST_IP" "$@"
}

ensure_ssh_key() {
    if [ ! -f "${KEY_NAME}.pub" ]; then
        mkdir -p "$(dirname "$KEY_NAME")"
        ssh-keygen -t rsa -b 4096 -f "$KEY_NAME" -C "PI-SSH-KEY" -N '' -q || {
            error "failed to create SSH key"
        }
    fi

    ssh-copy-id -i "${KEY_NAME}.pub" "$DEST_UN@$DEST_IP"
}

deploy_mediamtx() {
    scp_to_remote "$MEDIAMTX_DIR/mediamtx" "~/"
    scp_to_remote "$MEDIAMTX_DIR/mediamtx.yml" "~/"

    ssh_remote 'sudo install -d /usr/local/etc'
    ssh_remote 'sudo install -m 0755 "$HOME/mediamtx" /usr/local/bin/mediamtx'
    ssh_remote 'sudo install -m 0644 "$HOME/mediamtx.yml" /usr/local/etc/mediamtx.yml'
    ssh_remote 'rm -f "$HOME/mediamtx" "$HOME/mediamtx.yml"'
}

deploy_model() {
    scp_to_remote "$MODEL_DIR/efficientdet_lite0_int8.tflite" "~/"
    ssh_remote 'mkdir -p "$HOME/models"'
    ssh_remote 'install -m 0644 "$HOME/efficientdet_lite0_int8.tflite" "$HOME/models/efficientdet_lite0_int8.tflite"'
    ssh_remote 'rm -f "$HOME/efficientdet_lite0_int8.tflite"'
}

deploy_scripts() {
    scp_to_remote "$SCRIPTS_DIR/detector.py" "~/"
    scp_to_remote "$SCRIPTS_DIR/globals.py" "~/"
}

install_python_environment() {
    ssh_remote 'python3 -m venv --system-site-packages "$HOME/vision-env"'
    ssh_remote '"$HOME/vision-env/bin/python" -m pip install --upgrade pip'
    ssh_remote '"$HOME/vision-env/bin/python" -m pip install ai-edge-litert "numpy==1.26.4"'
}

install_system_services() {
    remote_user=$(ssh_remote 'id -un')

    scp_to_remote "$SERVICES_DIR/piatr-mediamtx.service" "~/"
    scp_to_remote "$SERVICES_DIR/piatr-detector.service" "~/"

    ssh_remote "sed -i 's/^User=.*/User=$remote_user/' \"\$HOME/piatr-detector.service\""
    ssh_remote 'sudo install -m 0644 "$HOME/piatr-mediamtx.service" /etc/systemd/system/piatr-mediamtx.service'
    ssh_remote 'sudo install -m 0644 "$HOME/piatr-detector.service" /etc/systemd/system/piatr-detector.service'
    ssh_remote 'rm -f "$HOME/piatr-mediamtx.service" "$HOME/piatr-detector.service"'
    ssh_remote 'sudo systemctl daemon-reload'
    ssh_remote 'sudo systemctl enable --now piatr-mediamtx.service piatr-detector.service'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -i)
            [ "$#" -ge 2 ] || error "Option -i requires an argument"
            DEST_IP=$2
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

[ -n "$DEST_IP" ] || usage

ensure_ssh_key

[ -x "$MEDIAMTX_DIR/mediamtx" ] || error "MediaMTX binary not found: $MEDIAMTX_DIR/mediamtx"
[ -f "$MEDIAMTX_DIR/mediamtx.yml" ] || error "MediaMTX config not found: $MEDIAMTX_DIR/mediamtx.yml"
[ -f "$MODEL_DIR/efficientdet_lite0_int8.tflite" ] || error "Model not found: $MODEL_DIR/efficientdet_lite0_int8.tflite"
[ -f "$SCRIPTS_DIR/detector.py" ] || error "Detector script not found: $SCRIPTS_DIR/detector.py"
[ -f "$SCRIPTS_DIR/globals.py" ] || error "Globals script not found: $SCRIPTS_DIR/globals.py"
[ -f "$SERVICES_DIR/piatr-mediamtx.service" ] || error "MediaMTX service not found: $SERVICES_DIR/piatr-mediamtx.service"
[ -f "$SERVICES_DIR/piatr-detector.service" ] || error "Detector service not found: $SERVICES_DIR/piatr-detector.service"

deploy_mediamtx
deploy_model
deploy_scripts
install_python_environment
install_system_services
