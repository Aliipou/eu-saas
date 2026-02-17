variable "environment" {
  type = string
}

variable "network_id" {
  type = number
}

variable "subnet_id" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "node_count" {
  type    = number
  default = 3
}

variable "server_type" {
  type    = string
  default = "cpx21"  # 3 vCPU, 4GB RAM — ~€8.5/month each
}

resource "hcloud_ssh_key" "deploy" {
  name       = "mt-platform-deploy-${var.environment}"
  public_key = var.ssh_public_key
}

resource "hcloud_server" "k8s_node" {
  count       = var.node_count
  name        = "k8s-node-${var.environment}-${count.index + 1}"
  server_type = var.server_type
  image       = "ubuntu-22.04"
  location    = "fsn1"  # Falkenstein, Germany — EU data residency
  ssh_keys    = [hcloud_ssh_key.deploy.id]

  labels = {
    environment = var.environment
    role        = count.index == 0 ? "control-plane" : "worker"
    managed-by  = "terraform"
  }

  network {
    network_id = var.network_id
  }

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail

    # Update and install prerequisites
    apt-get update && apt-get upgrade -y
    apt-get install -y curl apt-transport-https

    # Install k3s
    if [ ${count.index} -eq 0 ]; then
      curl -sfL https://get.k3s.io | sh -s - server \
        --disable traefik \
        --write-kubeconfig-mode 644 \
        --tls-san $(hostname -I | awk '{print $1}')
    else
      # Workers join the cluster (requires manual token setup)
      echo "Worker node ready for k3s agent installation"
    fi
  EOF
}

output "server_ips" {
  value = {
    for s in hcloud_server.k8s_node : s.name => s.ipv4_address
  }
}
