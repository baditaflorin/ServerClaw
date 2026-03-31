Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "__diesel_schema_migrations" {
  schema = schema.public
  column "version" {
    null = false
    type = character_varying(50)
  }
  column "run_on" {
    null    = false
    type    = timestamp
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.version]
  }
}
table "attachments" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "cipher_uuid" {
    null = false
    type = character_varying(40)
  }
  column "file_name" {
    null = false
    type = text
  }
  column "file_size" {
    null = false
    type = bigint
  }
  column "akey" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "attachments_cipher_uuid_fkey" {
    columns     = [column.cipher_uuid]
    ref_columns = [table.ciphers.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "auth_requests" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "user_uuid" {
    null = false
    type = character(36)
  }
  column "organization_uuid" {
    null = true
    type = character(36)
  }
  column "request_device_identifier" {
    null = false
    type = character(36)
  }
  column "device_type" {
    null = false
    type = integer
  }
  column "request_ip" {
    null = false
    type = text
  }
  column "response_device_id" {
    null = true
    type = character(36)
  }
  column "access_code" {
    null = false
    type = text
  }
  column "public_key" {
    null = false
    type = text
  }
  column "enc_key" {
    null = true
    type = text
  }
  column "master_password_hash" {
    null = true
    type = text
  }
  column "approved" {
    null = true
    type = boolean
  }
  column "creation_date" {
    null = false
    type = timestamp
  }
  column "response_date" {
    null = true
    type = timestamp
  }
  column "authentication_date" {
    null = true
    type = timestamp
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "auth_requests_organization_uuid_fkey" {
    columns     = [column.organization_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "auth_requests_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "ciphers" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null = false
    type = timestamp
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "user_uuid" {
    null = true
    type = character_varying(40)
  }
  column "organization_uuid" {
    null = true
    type = character_varying(40)
  }
  column "atype" {
    null = false
    type = integer
  }
  column "name" {
    null = false
    type = text
  }
  column "notes" {
    null = true
    type = text
  }
  column "fields" {
    null = true
    type = text
  }
  column "data" {
    null = false
    type = text
  }
  column "password_history" {
    null = true
    type = text
  }
  column "deleted_at" {
    null = true
    type = timestamp
  }
  column "reprompt" {
    null = true
    type = integer
  }
  column "key" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "ciphers_organization_uuid_fkey" {
    columns     = [column.organization_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ciphers_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "ciphers_collections" {
  schema = schema.public
  column "cipher_uuid" {
    null = false
    type = character_varying(40)
  }
  column "collection_uuid" {
    null = false
    type = character_varying(40)
  }
  primary_key {
    columns = [column.cipher_uuid, column.collection_uuid]
  }
  foreign_key "ciphers_collections_cipher_uuid_fkey" {
    columns     = [column.cipher_uuid]
    ref_columns = [table.ciphers.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ciphers_collections_collection_uuid_fkey" {
    columns     = [column.collection_uuid]
    ref_columns = [table.collections.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "collections" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "org_uuid" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = text
  }
  column "external_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "collections_org_uuid_fkey" {
    columns     = [column.org_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "collections_groups" {
  schema = schema.public
  column "collections_uuid" {
    null = false
    type = character_varying(40)
  }
  column "groups_uuid" {
    null = false
    type = character(36)
  }
  column "read_only" {
    null = false
    type = boolean
  }
  column "hide_passwords" {
    null = false
    type = boolean
  }
  column "manage" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.collections_uuid, column.groups_uuid]
  }
  foreign_key "collections_groups_collections_uuid_fkey" {
    columns     = [column.collections_uuid]
    ref_columns = [table.collections.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "collections_groups_groups_uuid_fkey" {
    columns     = [column.groups_uuid]
    ref_columns = [table.groups.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "devices" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null = false
    type = timestamp
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = text
  }
  column "atype" {
    null = false
    type = integer
  }
  column "push_token" {
    null = true
    type = text
  }
  column "refresh_token" {
    null = false
    type = text
  }
  column "twofactor_remember" {
    null = true
    type = text
  }
  column "push_uuid" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid, column.user_uuid]
  }
  foreign_key "devices_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "emergency_access" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "grantor_uuid" {
    null = true
    type = character(36)
  }
  column "grantee_uuid" {
    null = true
    type = character(36)
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "key_encrypted" {
    null = true
    type = text
  }
  column "atype" {
    null = false
    type = integer
  }
  column "status" {
    null = false
    type = integer
  }
  column "wait_time_days" {
    null = false
    type = integer
  }
  column "recovery_initiated_at" {
    null = true
    type = timestamp
  }
  column "last_notification_at" {
    null = true
    type = timestamp
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "created_at" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "emergency_access_grantee_uuid_fkey" {
    columns     = [column.grantee_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "emergency_access_grantor_uuid_fkey" {
    columns     = [column.grantor_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "event" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "event_type" {
    null = false
    type = integer
  }
  column "user_uuid" {
    null = true
    type = character(36)
  }
  column "org_uuid" {
    null = true
    type = character(36)
  }
  column "cipher_uuid" {
    null = true
    type = character(36)
  }
  column "collection_uuid" {
    null = true
    type = character(36)
  }
  column "group_uuid" {
    null = true
    type = character(36)
  }
  column "org_user_uuid" {
    null = true
    type = character(36)
  }
  column "act_user_uuid" {
    null = true
    type = character(36)
  }
  column "device_type" {
    null = true
    type = integer
  }
  column "ip_address" {
    null = true
    type = text
  }
  column "event_date" {
    null = false
    type = timestamp
  }
  column "policy_uuid" {
    null = true
    type = character(36)
  }
  column "provider_uuid" {
    null = true
    type = character(36)
  }
  column "provider_user_uuid" {
    null = true
    type = character(36)
  }
  column "provider_org_uuid" {
    null = true
    type = character(36)
  }
  primary_key {
    columns = [column.uuid]
  }
}
table "favorites" {
  schema = schema.public
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "cipher_uuid" {
    null = false
    type = character_varying(40)
  }
  primary_key {
    columns = [column.user_uuid, column.cipher_uuid]
  }
  foreign_key "favorites_cipher_uuid_fkey" {
    columns     = [column.cipher_uuid]
    ref_columns = [table.ciphers.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "favorites_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "folders" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null = false
    type = timestamp
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "folders_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "folders_ciphers" {
  schema = schema.public
  column "cipher_uuid" {
    null = false
    type = character_varying(40)
  }
  column "folder_uuid" {
    null = false
    type = character_varying(40)
  }
  primary_key {
    columns = [column.cipher_uuid, column.folder_uuid]
  }
  foreign_key "folders_ciphers_cipher_uuid_fkey" {
    columns     = [column.cipher_uuid]
    ref_columns = [table.ciphers.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "folders_ciphers_folder_uuid_fkey" {
    columns     = [column.folder_uuid]
    ref_columns = [table.folders.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "groups" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "organizations_uuid" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "access_all" {
    null = false
    type = boolean
  }
  column "external_id" {
    null = true
    type = character_varying(300)
  }
  column "creation_date" {
    null = false
    type = timestamp
  }
  column "revision_date" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "groups_organizations_uuid_fkey" {
    columns     = [column.organizations_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "groups_users" {
  schema = schema.public
  column "groups_uuid" {
    null = false
    type = character(36)
  }
  column "users_organizations_uuid" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.groups_uuid, column.users_organizations_uuid]
  }
  foreign_key "groups_users_groups_uuid_fkey" {
    columns     = [column.groups_uuid]
    ref_columns = [table.groups.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "groups_users_users_organizations_uuid_fkey" {
    columns     = [column.users_organizations_uuid]
    ref_columns = [table.users_organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "invitations" {
  schema = schema.public
  column "email" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.email]
  }
}
table "org_policies" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "org_uuid" {
    null = false
    type = character(36)
  }
  column "atype" {
    null = false
    type = integer
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "data" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "org_policies_org_uuid_fkey" {
    columns     = [column.org_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "org_policies_org_uuid_atype_key" {
    columns = [column.org_uuid, column.atype]
  }
}
table "organization_api_key" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "org_uuid" {
    null = false
    type = character(36)
  }
  column "atype" {
    null = false
    type = integer
  }
  column "api_key" {
    null = true
    type = character_varying(255)
  }
  column "revision_date" {
    null = false
    type = timestamp
  }
  primary_key {
    columns = [column.uuid, column.org_uuid]
  }
  foreign_key "organization_api_key_org_uuid_fkey" {
    columns     = [column.org_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "organizations" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "name" {
    null = false
    type = text
  }
  column "billing_email" {
    null = false
    type = text
  }
  column "private_key" {
    null = true
    type = text
  }
  column "public_key" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
}
table "sends" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character(36)
  }
  column "user_uuid" {
    null = true
    type = character(36)
  }
  column "organization_uuid" {
    null = true
    type = character(36)
  }
  column "name" {
    null = false
    type = text
  }
  column "notes" {
    null = true
    type = text
  }
  column "atype" {
    null = false
    type = integer
  }
  column "data" {
    null = false
    type = text
  }
  column "akey" {
    null = false
    type = text
  }
  column "password_hash" {
    null = true
    type = bytea
  }
  column "password_salt" {
    null = true
    type = bytea
  }
  column "password_iter" {
    null = true
    type = integer
  }
  column "max_access_count" {
    null = true
    type = integer
  }
  column "access_count" {
    null = false
    type = integer
  }
  column "creation_date" {
    null = false
    type = timestamp
  }
  column "revision_date" {
    null = false
    type = timestamp
  }
  column "expiration_date" {
    null = true
    type = timestamp
  }
  column "deletion_date" {
    null = false
    type = timestamp
  }
  column "disabled" {
    null = false
    type = boolean
  }
  column "hide_email" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "sends_organization_uuid_fkey" {
    columns     = [column.organization_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sends_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "sso_auth" {
  schema = schema.public
  column "state" {
    null = false
    type = text
  }
  column "client_challenge" {
    null = false
    type = text
  }
  column "nonce" {
    null = false
    type = text
  }
  column "redirect_uri" {
    null = false
    type = text
  }
  column "code_response" {
    null = true
    type = text
  }
  column "auth_response" {
    null = true
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  column "updated_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.state]
  }
}
table "sso_users" {
  schema = schema.public
  column "user_uuid" {
    null = false
    type = character(36)
  }
  column "identifier" {
    null = false
    type = text
  }
  column "created_at" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.user_uuid]
  }
  foreign_key "sso_users_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  unique "sso_users_identifier_key" {
    columns = [column.identifier]
  }
}
table "twofactor" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "atype" {
    null = false
    type = integer
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "data" {
    null = false
    type = text
  }
  column "last_used" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "twofactor_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "twofactor_user_uuid_atype_key" {
    columns = [column.user_uuid, column.atype]
  }
}
table "twofactor_duo_ctx" {
  schema = schema.public
  column "state" {
    null = false
    type = character_varying(64)
  }
  column "user_email" {
    null = false
    type = character_varying(255)
  }
  column "nonce" {
    null = false
    type = character_varying(64)
  }
  column "exp" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.state]
  }
}
table "twofactor_incomplete" {
  schema = schema.public
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "device_uuid" {
    null = false
    type = character_varying(40)
  }
  column "device_name" {
    null = false
    type = text
  }
  column "login_time" {
    null = false
    type = timestamp
  }
  column "ip_address" {
    null = false
    type = text
  }
  column "device_type" {
    null    = false
    type    = integer
    default = 14
  }
  primary_key {
    columns = [column.user_uuid, column.device_uuid]
  }
  foreign_key "twofactor_incomplete_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "users" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "created_at" {
    null = false
    type = timestamp
  }
  column "updated_at" {
    null = false
    type = timestamp
  }
  column "email" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "password_hash" {
    null = false
    type = bytea
  }
  column "salt" {
    null = false
    type = bytea
  }
  column "password_iterations" {
    null = false
    type = integer
  }
  column "password_hint" {
    null = true
    type = text
  }
  column "akey" {
    null = false
    type = text
  }
  column "private_key" {
    null = true
    type = text
  }
  column "public_key" {
    null = true
    type = text
  }
  column "totp_secret" {
    null = true
    type = text
  }
  column "totp_recover" {
    null = true
    type = text
  }
  column "security_stamp" {
    null = false
    type = text
  }
  column "equivalent_domains" {
    null = false
    type = text
  }
  column "excluded_globals" {
    null = false
    type = text
  }
  column "client_kdf_type" {
    null    = false
    type    = integer
    default = 0
  }
  column "client_kdf_iter" {
    null    = false
    type    = integer
    default = 100000
  }
  column "verified_at" {
    null = true
    type = timestamp
  }
  column "last_verifying_at" {
    null = true
    type = timestamp
  }
  column "login_verify_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "email_new" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "email_new_token" {
    null    = true
    type    = character_varying(16)
    default = sql("NULL::character varying")
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "stamp_exception" {
    null = true
    type = text
  }
  column "api_key" {
    null = true
    type = text
  }
  column "avatar_color" {
    null = true
    type = text
  }
  column "client_kdf_memory" {
    null = true
    type = integer
  }
  column "client_kdf_parallelism" {
    null = true
    type = integer
  }
  column "external_id" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  unique "users_email_key" {
    columns = [column.email]
  }
}
table "users_collections" {
  schema = schema.public
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "collection_uuid" {
    null = false
    type = character_varying(40)
  }
  column "read_only" {
    null    = false
    type    = boolean
    default = false
  }
  column "hide_passwords" {
    null    = false
    type    = boolean
    default = false
  }
  column "manage" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.user_uuid, column.collection_uuid]
  }
  foreign_key "users_collections_collection_uuid_fkey" {
    columns     = [column.collection_uuid]
    ref_columns = [table.collections.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_collections_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "users_organizations" {
  schema = schema.public
  column "uuid" {
    null = false
    type = character_varying(40)
  }
  column "user_uuid" {
    null = false
    type = character_varying(40)
  }
  column "org_uuid" {
    null = false
    type = character_varying(40)
  }
  column "access_all" {
    null = false
    type = boolean
  }
  column "akey" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = integer
  }
  column "atype" {
    null = false
    type = integer
  }
  column "reset_password_key" {
    null = true
    type = text
  }
  column "external_id" {
    null = true
    type = text
  }
  column "invited_by_email" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.uuid]
  }
  foreign_key "users_organizations_org_uuid_fkey" {
    columns     = [column.org_uuid]
    ref_columns = [table.organizations.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_organizations_user_uuid_fkey" {
    columns     = [column.user_uuid]
    ref_columns = [table.users.column.uuid]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "users_organizations_user_uuid_org_uuid_key" {
    columns = [column.user_uuid, column.org_uuid]
  }
}
schema "public" {
  comment = "standard public schema"
}
