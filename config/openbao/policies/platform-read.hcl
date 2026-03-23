path "kv/data/*" {
  capabilities = ["read", "list"]
}

path "kv/metadata/*" {
  capabilities = ["read", "list"]
}

path "database/creds/*" {
  capabilities = ["read"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "sys/health" {
  capabilities = ["read", "sudo"]
}
