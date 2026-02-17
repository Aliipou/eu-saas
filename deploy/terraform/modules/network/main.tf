variable "environment" {
  type = string
}

resource "hcloud_network" "main" {
  name     = "mt-platform-${var.environment}"
  ip_range = "10.0.0.0/16"
}

resource "hcloud_network_subnet" "k8s" {
  network_id   = hcloud_network.main.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = "10.0.1.0/24"
}

resource "hcloud_firewall" "k8s" {
  name = "mt-k8s-${var.environment}"

  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "6443"
    source_ips = ["0.0.0.0/0"]
    description = "Kubernetes API"
  }

  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "80"
    source_ips = ["0.0.0.0/0"]
    description = "HTTP"
  }

  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "443"
    source_ips = ["0.0.0.0/0"]
    description = "HTTPS"
  }

  rule {
    direction = "in"
    protocol  = "tcp"
    port      = "22"
    source_ips = ["0.0.0.0/0"]
    description = "SSH"
  }
}

output "network_id" {
  value = hcloud_network.main.id
}

output "subnet_id" {
  value = hcloud_network_subnet.k8s.id
}

output "firewall_id" {
  value = hcloud_firewall.k8s.id
}
