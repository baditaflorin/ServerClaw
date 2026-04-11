terraform {
  backend "s3" {
    bucket                      = "tofu-state"
    key                         = "staging/terraform.tfstate"
    region                      = "main"
    endpoints                   = { s3 = "https://minio.example.com" }
    use_path_style              = true
    use_lockfile                = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    skip_region_validation      = true
  }
}
