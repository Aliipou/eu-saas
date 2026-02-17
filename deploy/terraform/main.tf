terraform {
  required_version = ">= 1.7.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }

  backend "s3" {
    bucket                      = "mt-platform-tfstate"
    key                         = "infrastructure/terraform.tfstate"
    region                      = "eu-central-1"
    endpoint                    = "https://fsn1.your-objectstorage.com"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "environment" {
  type    = string
  default = "production"
}

variable "ssh_public_key" {
  type = string
}

module "network" {
  source      = "./modules/network"
  environment = var.environment
}

module "compute" {
  source         = "./modules/compute"
  environment    = var.environment
  network_id     = module.network.network_id
  subnet_id      = module.network.subnet_id
  ssh_public_key = var.ssh_public_key
}

module "database" {
  source      = "./modules/database"
  environment = var.environment
  network_id  = module.network.network_id
}

output "server_ips" {
  value = module.compute.server_ips
}

output "database_host" {
  value     = module.database.host
  sensitive = true
}
