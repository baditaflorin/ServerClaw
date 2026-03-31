Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "admin_event_entity" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "admin_event_time" {
    null = true
    type = bigint
  }
  column "realm_id" {
    null = true
    type = character_varying(255)
  }
  column "operation_type" {
    null = true
    type = character_varying(255)
  }
  column "auth_realm_id" {
    null = true
    type = character_varying(255)
  }
  column "auth_client_id" {
    null = true
    type = character_varying(255)
  }
  column "auth_user_id" {
    null = true
    type = character_varying(255)
  }
  column "ip_address" {
    null = true
    type = character_varying(255)
  }
  column "resource_path" {
    null = true
    type = character_varying(2550)
  }
  column "representation" {
    null = true
    type = text
  }
  column "error" {
    null = true
    type = character_varying(255)
  }
  column "resource_type" {
    null = true
    type = character_varying(64)
  }
  column "details_json" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_admin_event_time" {
    columns = [column.realm_id, column.admin_event_time]
  }
}
table "associated_policy" {
  schema = schema.public
  column "policy_id" {
    null = false
    type = character_varying(36)
  }
  column "associated_policy_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.policy_id, column.associated_policy_id]
  }
  foreign_key "fk_frsr5s213xcx4wnkog82ssrfy" {
    columns     = [column.associated_policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrpas14xcx4wnkog82ssrfy" {
    columns     = [column.policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_assoc_pol_assoc_pol_id" {
    columns = [column.associated_policy_id]
  }
}
table "authentication_execution" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "alias" {
    null = true
    type = character_varying(255)
  }
  column "authenticator" {
    null = true
    type = character_varying(36)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "flow_id" {
    null = true
    type = character_varying(36)
  }
  column "requirement" {
    null = true
    type = integer
  }
  column "priority" {
    null = true
    type = integer
  }
  column "authenticator_flow" {
    null    = false
    type    = boolean
    default = false
  }
  column "auth_flow_id" {
    null = true
    type = character_varying(36)
  }
  column "auth_config" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_auth_exec_flow" {
    columns     = [column.flow_id]
    ref_columns = [table.authentication_flow.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_auth_exec_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_auth_exec_flow" {
    columns = [column.flow_id]
  }
  index "idx_auth_exec_realm_flow" {
    columns = [column.realm_id, column.flow_id]
  }
}
table "authentication_flow" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "alias" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "provider_id" {
    null    = false
    type    = character_varying(36)
    default = "basic-flow"
  }
  column "top_level" {
    null    = false
    type    = boolean
    default = false
  }
  column "built_in" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_auth_flow_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_auth_flow_realm" {
    columns = [column.realm_id]
  }
}
table "authenticator_config" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "alias" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_auth_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_auth_config_realm" {
    columns = [column.realm_id]
  }
}
table "authenticator_config_entry" {
  schema = schema.public
  column "authenticator_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.authenticator_id, column.name]
  }
}
table "broker_link" {
  schema = schema.public
  column "identity_provider" {
    null = false
    type = character_varying(255)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "broker_user_id" {
    null = true
    type = character_varying(255)
  }
  column "broker_username" {
    null = true
    type = character_varying(255)
  }
  column "token" {
    null = true
    type = text
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.identity_provider, column.user_id]
  }
  index "idx_broker_link_identity_provider" {
    columns = [column.realm_id, column.identity_provider, column.broker_user_id]
  }
  index "idx_broker_link_user_id" {
    columns = [column.user_id]
  }
}
table "client" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "full_scope_allowed" {
    null    = false
    type    = boolean
    default = false
  }
  column "client_id" {
    null = true
    type = character_varying(255)
  }
  column "not_before" {
    null = true
    type = integer
  }
  column "public_client" {
    null    = false
    type    = boolean
    default = false
  }
  column "secret" {
    null = true
    type = character_varying(255)
  }
  column "base_url" {
    null = true
    type = character_varying(255)
  }
  column "bearer_only" {
    null    = false
    type    = boolean
    default = false
  }
  column "management_url" {
    null = true
    type = character_varying(255)
  }
  column "surrogate_auth_required" {
    null    = false
    type    = boolean
    default = false
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "protocol" {
    null = true
    type = character_varying(255)
  }
  column "node_rereg_timeout" {
    null    = true
    type    = integer
    default = 0
  }
  column "frontchannel_logout" {
    null    = false
    type    = boolean
    default = false
  }
  column "consent_required" {
    null    = false
    type    = boolean
    default = false
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "service_accounts_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "client_authenticator_type" {
    null = true
    type = character_varying(255)
  }
  column "root_url" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "registration_token" {
    null = true
    type = character_varying(255)
  }
  column "standard_flow_enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "implicit_flow_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "direct_access_grants_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "always_display_in_console" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_client_id" {
    columns = [column.client_id]
  }
  unique "uk_b71cjlbenv945rb6gcon438at" {
    columns = [column.realm_id, column.client_id]
  }
}
table "client_attributes" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.client_id, column.name]
  }
  foreign_key "fk3c47c64beacca966" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_client_att_by_name_value" {
    on {
      column = column.name
    }
    on {
      expr = "substr(value, 1, 255)"
    }
  }
}
table "client_auth_flow_bindings" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "flow_id" {
    null = true
    type = character_varying(36)
  }
  column "binding_name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.client_id, column.binding_name]
  }
}
table "client_initial_access" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "timestamp" {
    null = true
    type = integer
  }
  column "expiration" {
    null = true
    type = integer
  }
  column "count" {
    null = true
    type = integer
  }
  column "remaining_count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_client_init_acc_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_client_init_acc_realm" {
    columns = [column.realm_id]
  }
}
table "client_node_registrations" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = integer
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.client_id, column.name]
  }
  foreign_key "fk4129723ba992f594" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "client_scope" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "protocol" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_realm_clscope" {
    columns = [column.realm_id]
  }
  unique "uk_cli_scope" {
    columns = [column.realm_id, column.name]
  }
}
table "client_scope_attributes" {
  schema = schema.public
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = character_varying(2048)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.scope_id, column.name]
  }
  foreign_key "fk_cl_scope_attr_scope" {
    columns     = [column.scope_id]
    ref_columns = [table.client_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_clscope_attrs" {
    columns = [column.scope_id]
  }
}
table "client_scope_client" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "scope_id" {
    null = false
    type = character_varying(255)
  }
  column "default_scope" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.client_id, column.scope_id]
  }
  index "idx_cl_clscope" {
    columns = [column.scope_id]
  }
  index "idx_clscope_cl" {
    columns = [column.client_id]
  }
}
table "client_scope_role_mapping" {
  schema = schema.public
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  column "role_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.scope_id, column.role_id]
  }
  foreign_key "fk_cl_scope_rm_scope" {
    columns     = [column.scope_id]
    ref_columns = [table.client_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_clscope_role" {
    columns = [column.scope_id]
  }
  index "idx_role_clscope" {
    columns = [column.role_id]
  }
}
table "component" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "parent_id" {
    null = true
    type = character_varying(36)
  }
  column "provider_id" {
    null = true
    type = character_varying(36)
  }
  column "provider_type" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "sub_type" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_component_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_component_provider_type" {
    columns = [column.provider_type]
  }
  index "idx_component_realm" {
    columns = [column.realm_id]
  }
}
table "component_config" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "component_id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_component_config" {
    columns     = [column.component_id]
    ref_columns = [table.component.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_compo_config_compo" {
    columns = [column.component_id]
  }
}
table "composite_role" {
  schema = schema.public
  column "composite" {
    null = false
    type = character_varying(36)
  }
  column "child_role" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.composite, column.child_role]
  }
  foreign_key "fk_a63wvekftu8jo1pnj81e7mce2" {
    columns     = [column.composite]
    ref_columns = [table.keycloak_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_gr7thllb9lu8q4vqa4524jjy8" {
    columns     = [column.child_role]
    ref_columns = [table.keycloak_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_composite" {
    columns = [column.composite]
  }
  index "idx_composite_child" {
    columns = [column.child_role]
  }
}
table "credential" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "salt" {
    null = true
    type = bytea
  }
  column "type" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = true
    type = character_varying(36)
  }
  column "created_date" {
    null = true
    type = bigint
  }
  column "user_label" {
    null = true
    type = character_varying(255)
  }
  column "secret_data" {
    null = true
    type = text
  }
  column "credential_data" {
    null = true
    type = text
  }
  column "priority" {
    null = true
    type = integer
  }
  column "version" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_pfyr0glasqyl0dei3kl69r6v0" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_credential" {
    columns = [column.user_id]
  }
}
table "databasechangelog" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "author" {
    null = false
    type = character_varying(255)
  }
  column "filename" {
    null = false
    type = character_varying(255)
  }
  column "dateexecuted" {
    null = false
    type = timestamp
  }
  column "orderexecuted" {
    null = false
    type = integer
  }
  column "exectype" {
    null = false
    type = character_varying(10)
  }
  column "md5sum" {
    null = true
    type = character_varying(35)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "comments" {
    null = true
    type = character_varying(255)
  }
  column "tag" {
    null = true
    type = character_varying(255)
  }
  column "liquibase" {
    null = true
    type = character_varying(20)
  }
  column "contexts" {
    null = true
    type = character_varying(255)
  }
  column "labels" {
    null = true
    type = character_varying(255)
  }
  column "deployment_id" {
    null = true
    type = character_varying(10)
  }
}
table "databasechangeloglock" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
  }
  column "locked" {
    null = false
    type = boolean
  }
  column "lockgranted" {
    null = true
    type = timestamp
  }
  column "lockedby" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
}
table "default_client_scope" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  column "default_scope" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.realm_id, column.scope_id]
  }
  foreign_key "fk_r_def_cli_scope_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_defcls_realm" {
    columns = [column.realm_id]
  }
  index "idx_defcls_scope" {
    columns = [column.scope_id]
  }
}
table "event_entity" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "client_id" {
    null = true
    type = character_varying(255)
  }
  column "details_json" {
    null = true
    type = character_varying(2550)
  }
  column "error" {
    null = true
    type = character_varying(255)
  }
  column "ip_address" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(255)
  }
  column "session_id" {
    null = true
    type = character_varying(255)
  }
  column "event_time" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = true
    type = character_varying(255)
  }
  column "details_json_long_value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_event_entity_user_id_type" {
    columns = [column.user_id, column.type, column.event_time]
  }
  index "idx_event_time" {
    columns = [column.realm_id, column.event_time]
  }
}
table "fed_user_attribute" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = character_varying(2024)
  }
  column "long_value_hash" {
    null = true
    type = bytea
  }
  column "long_value_hash_lower_case" {
    null = true
    type = bytea
  }
  column "long_value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "fed_user_attr_long_values" {
    columns = [column.long_value_hash, column.name]
  }
  index "fed_user_attr_long_values_lower_case" {
    columns = [column.long_value_hash_lower_case, column.name]
  }
  index "idx_fu_attribute" {
    columns = [column.user_id, column.realm_id, column.name]
  }
}
table "fed_user_consent" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "client_id" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  column "created_date" {
    null = true
    type = bigint
  }
  column "last_updated_date" {
    null = true
    type = bigint
  }
  column "client_storage_provider" {
    null = true
    type = character_varying(36)
  }
  column "external_client_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_fu_cnsnt_ext" {
    columns = [column.user_id, column.client_storage_provider, column.external_client_id]
  }
  index "idx_fu_consent" {
    columns = [column.user_id, column.client_id]
  }
  index "idx_fu_consent_ru" {
    columns = [column.realm_id, column.user_id]
  }
}
table "fed_user_consent_cl_scope" {
  schema = schema.public
  column "user_consent_id" {
    null = false
    type = character_varying(36)
  }
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.user_consent_id, column.scope_id]
  }
}
table "fed_user_credential" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "salt" {
    null = true
    type = bytea
  }
  column "type" {
    null = true
    type = character_varying(255)
  }
  column "created_date" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  column "user_label" {
    null = true
    type = character_varying(255)
  }
  column "secret_data" {
    null = true
    type = text
  }
  column "credential_data" {
    null = true
    type = text
  }
  column "priority" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_fu_credential" {
    columns = [column.user_id, column.type]
  }
  index "idx_fu_credential_ru" {
    columns = [column.realm_id, column.user_id]
  }
}
table "fed_user_group_membership" {
  schema = schema.public
  column "group_id" {
    null = false
    type = character_varying(36)
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.group_id, column.user_id]
  }
  index "idx_fu_group_membership" {
    columns = [column.user_id, column.group_id]
  }
  index "idx_fu_group_membership_ru" {
    columns = [column.realm_id, column.user_id]
  }
}
table "fed_user_required_action" {
  schema = schema.public
  column "required_action" {
    null    = false
    type    = character_varying(255)
    default = " "
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.required_action, column.user_id]
  }
  index "idx_fu_required_action" {
    columns = [column.user_id, column.required_action]
  }
  index "idx_fu_required_action_ru" {
    columns = [column.realm_id, column.user_id]
  }
}
table "fed_user_role_mapping" {
  schema = schema.public
  column "role_id" {
    null = false
    type = character_varying(36)
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.role_id, column.user_id]
  }
  index "idx_fu_role_mapping" {
    columns = [column.user_id, column.role_id]
  }
  index "idx_fu_role_mapping_ru" {
    columns = [column.realm_id, column.user_id]
  }
}
table "federated_identity" {
  schema = schema.public
  column "identity_provider" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "federated_user_id" {
    null = true
    type = character_varying(255)
  }
  column "federated_username" {
    null = true
    type = character_varying(255)
  }
  column "token" {
    null = true
    type = text
  }
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.identity_provider, column.user_id]
  }
  foreign_key "fk404288b92ef007a6" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_fedidentity_feduser" {
    columns = [column.federated_user_id]
  }
  index "idx_fedidentity_user" {
    columns = [column.user_id]
  }
}
table "federated_user" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "storage_provider_id" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
}
table "group_attribute" {
  schema = schema.public
  column "id" {
    null    = false
    type    = character_varying(36)
    default = "sybase-needs-something-here"
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "group_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_group_attribute_group" {
    columns     = [column.group_id]
    ref_columns = [table.keycloak_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_group_att_by_name_value" {
    on {
      column = column.name
    }
    on {
      expr = "((value)::character varying(250))"
    }
  }
  index "idx_group_attr_group" {
    columns = [column.group_id]
  }
}
table "group_role_mapping" {
  schema = schema.public
  column "role_id" {
    null = false
    type = character_varying(36)
  }
  column "group_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.role_id, column.group_id]
  }
  foreign_key "fk_group_role_group" {
    columns     = [column.group_id]
    ref_columns = [table.keycloak_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_group_role_mapp_group" {
    columns = [column.group_id]
  }
}
table "identity_provider" {
  schema = schema.public
  column "internal_id" {
    null = false
    type = character_varying(36)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "provider_alias" {
    null = true
    type = character_varying(255)
  }
  column "provider_id" {
    null = true
    type = character_varying(255)
  }
  column "store_token" {
    null = true
    type = boolean
  }
  column "authenticate_by_default" {
    null = true
    type = boolean
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "add_token_role" {
    null = true
    type = boolean
  }
  column "trust_email" {
    null = true
    type = boolean
  }
  column "first_broker_login_flow_id" {
    null = true
    type = character_varying(36)
  }
  column "post_broker_login_flow_id" {
    null = true
    type = character_varying(36)
  }
  column "provider_display_name" {
    null = true
    type = character_varying(255)
  }
  column "link_only" {
    null = true
    type = boolean
  }
  column "organization_id" {
    null = true
    type = character_varying(255)
  }
  column "hide_on_login" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.internal_id]
  }
  foreign_key "fk2b4ebc52ae5c3b34" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_ident_prov_realm" {
    columns = [column.realm_id]
  }
  index "idx_idp_for_login" {
    columns = [column.realm_id, column.enabled, column.link_only, column.hide_on_login, column.organization_id]
  }
  index "idx_idp_realm_org" {
    columns = [column.realm_id, column.organization_id]
  }
  unique "uk_2daelwnibji49avxsrtuf6xj33" {
    columns = [column.provider_alias, column.realm_id]
  }
}
table "identity_provider_config" {
  schema = schema.public
  column "identity_provider_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.identity_provider_id, column.name]
  }
  foreign_key "fkdc4897cf864c4e43" {
    columns     = [column.identity_provider_id]
    ref_columns = [table.identity_provider.column.internal_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "identity_provider_mapper" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "idp_alias" {
    null = false
    type = character_varying(255)
  }
  column "idp_mapper_name" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_idpm_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_id_prov_mapp_realm" {
    columns = [column.realm_id]
  }
}
table "idp_mapper_config" {
  schema = schema.public
  column "idp_mapper_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.idp_mapper_id, column.name]
  }
  foreign_key "fk_idpmconfig" {
    columns     = [column.idp_mapper_id]
    ref_columns = [table.identity_provider_mapper.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "jgroups_ping" {
  schema = schema.public
  column "address" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = true
    type = character_varying(200)
  }
  column "cluster_name" {
    null = false
    type = character_varying(200)
  }
  column "ip" {
    null = false
    type = character_varying(200)
  }
  column "coord" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.address]
  }
}
table "keycloak_group" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "parent_group" {
    null = false
    type = character_varying(36)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "type" {
    null    = false
    type    = integer
    default = 0
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  unique "sibling_names" {
    columns = [column.realm_id, column.parent_group, column.name]
  }
}
table "keycloak_role" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "client_realm_constraint" {
    null = true
    type = character_varying(255)
  }
  column "client_role" {
    null    = false
    type    = boolean
    default = false
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(255)
  }
  column "client" {
    null = true
    type = character_varying(36)
  }
  column "realm" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_6vyqfe4cn4wlq8r6kt5vdsj5c" {
    columns     = [column.realm]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_keycloak_role_client" {
    columns = [column.client]
  }
  index "idx_keycloak_role_realm" {
    columns = [column.realm]
  }
  unique "UK_J3RWUVD56ONTGSUHOGM184WW2-2" {
    columns = [column.name, column.client_realm_constraint]
  }
}
table "migration_model" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "version" {
    null = true
    type = character_varying(36)
  }
  column "update_time" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_update_time" {
    columns = [column.update_time]
  }
  unique "uk_migration_update_time" {
    columns = [column.update_time]
  }
  unique "uk_migration_version" {
    columns = [column.version]
  }
}
table "offline_client_session" {
  schema = schema.public
  column "user_session_id" {
    null = false
    type = character_varying(36)
  }
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "offline_flag" {
    null = false
    type = character_varying(4)
  }
  column "timestamp" {
    null = true
    type = integer
  }
  column "data" {
    null = true
    type = text
  }
  column "client_storage_provider" {
    null    = false
    type    = character_varying(36)
    default = "local"
  }
  column "external_client_id" {
    null    = false
    type    = character_varying(255)
    default = "local"
  }
  column "version" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.user_session_id, column.client_id, column.client_storage_provider, column.external_client_id, column.offline_flag]
  }
  index "idx_offline_css_by_client" {
    columns = [column.client_id, column.offline_flag]
    where   = "((client_id)::text <> 'external'::text)"
  }
  index "idx_offline_css_by_client_storage_provider" {
    columns = [column.client_storage_provider, column.external_client_id, column.offline_flag]
    where   = "((client_storage_provider)::text <> 'internal'::text)"
  }
}
table "offline_user_session" {
  schema = schema.public
  column "user_session_id" {
    null = false
    type = character_varying(36)
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "created_on" {
    null = false
    type = integer
  }
  column "offline_flag" {
    null = false
    type = character_varying(4)
  }
  column "data" {
    null = true
    type = text
  }
  column "last_session_refresh" {
    null    = false
    type    = integer
    default = 0
  }
  column "broker_session_id" {
    null = true
    type = character_varying(1024)
  }
  column "version" {
    null    = true
    type    = integer
    default = 0
  }
  column "remember_me" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.user_session_id, column.offline_flag]
  }
  index "idx_offline_uss_by_broker_session_id" {
    columns = [column.broker_session_id, column.realm_id]
  }
  index "idx_offline_uss_by_user" {
    columns = [column.user_id, column.realm_id, column.offline_flag]
  }
  index "idx_user_session_expiration_created" {
    columns = [column.realm_id, column.offline_flag, column.remember_me, column.created_on, column.user_session_id, column.user_id]
  }
  index "idx_user_session_expiration_last_refresh" {
    columns = [column.realm_id, column.offline_flag, column.remember_me, column.last_session_refresh, column.user_session_id, column.user_id]
  }
}
table "org" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "realm_id" {
    null = false
    type = character_varying(255)
  }
  column "group_id" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(4000)
  }
  column "alias" {
    null = false
    type = character_varying(255)
  }
  column "redirect_url" {
    null = true
    type = character_varying(2048)
  }
  primary_key {
    columns = [column.id]
  }
  unique "uk_org_alias" {
    columns = [column.realm_id, column.alias]
  }
  unique "uk_org_group" {
    columns = [column.group_id]
  }
  unique "uk_org_name" {
    columns = [column.realm_id, column.name]
  }
}
table "org_domain" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "verified" {
    null = false
    type = boolean
  }
  column "org_id" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id, column.name]
  }
  index "idx_org_domain_org_id" {
    columns = [column.org_id]
  }
}
table "org_invitation" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "organization_id" {
    null = false
    type = character_varying(255)
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "first_name" {
    null = true
    type = character_varying(255)
  }
  column "last_name" {
    null = true
    type = character_varying(255)
  }
  column "created_at" {
    null = false
    type = integer
  }
  column "expires_at" {
    null = true
    type = integer
  }
  column "invite_link" {
    null = true
    type = character_varying(2048)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_org_invitation_org" {
    columns     = [column.organization_id]
    ref_columns = [table.org.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_org_invitation_email" {
    columns = [column.email]
  }
  index "idx_org_invitation_expires" {
    columns = [column.expires_at]
  }
  index "idx_org_invitation_org_id" {
    columns = [column.organization_id]
  }
  unique "uk_org_invitation_email" {
    columns = [column.organization_id, column.email]
  }
}
table "policy_config" {
  schema = schema.public
  column "policy_id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.policy_id, column.name]
  }
  foreign_key "fkdc34197cf864c4e43" {
    columns     = [column.policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "protocol_mapper" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "protocol" {
    null = false
    type = character_varying(255)
  }
  column "protocol_mapper_name" {
    null = false
    type = character_varying(255)
  }
  column "client_id" {
    null = true
    type = character_varying(36)
  }
  column "client_scope_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_cli_scope_mapper" {
    columns     = [column.client_scope_id]
    ref_columns = [table.client_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_pcm_realm" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_clscope_protmap" {
    columns = [column.client_scope_id]
  }
  index "idx_protocol_mapper_client" {
    columns = [column.client_id]
  }
}
table "protocol_mapper_config" {
  schema = schema.public
  column "protocol_mapper_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.protocol_mapper_id, column.name]
  }
  foreign_key "fk_pmconfig" {
    columns     = [column.protocol_mapper_id]
    ref_columns = [table.protocol_mapper.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "realm" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "access_code_lifespan" {
    null = true
    type = integer
  }
  column "user_action_lifespan" {
    null = true
    type = integer
  }
  column "access_token_lifespan" {
    null = true
    type = integer
  }
  column "account_theme" {
    null = true
    type = character_varying(255)
  }
  column "admin_theme" {
    null = true
    type = character_varying(255)
  }
  column "email_theme" {
    null = true
    type = character_varying(255)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "events_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "events_expiration" {
    null = true
    type = bigint
  }
  column "login_theme" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "not_before" {
    null = true
    type = integer
  }
  column "password_policy" {
    null = true
    type = character_varying(2550)
  }
  column "registration_allowed" {
    null    = false
    type    = boolean
    default = false
  }
  column "remember_me" {
    null    = false
    type    = boolean
    default = false
  }
  column "reset_password_allowed" {
    null    = false
    type    = boolean
    default = false
  }
  column "social" {
    null    = false
    type    = boolean
    default = false
  }
  column "ssl_required" {
    null = true
    type = character_varying(255)
  }
  column "sso_idle_timeout" {
    null = true
    type = integer
  }
  column "sso_max_lifespan" {
    null = true
    type = integer
  }
  column "update_profile_on_soc_login" {
    null    = false
    type    = boolean
    default = false
  }
  column "verify_email" {
    null    = false
    type    = boolean
    default = false
  }
  column "master_admin_client" {
    null = true
    type = character_varying(36)
  }
  column "login_lifespan" {
    null = true
    type = integer
  }
  column "internationalization_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "default_locale" {
    null = true
    type = character_varying(255)
  }
  column "reg_email_as_username" {
    null    = false
    type    = boolean
    default = false
  }
  column "admin_events_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "admin_events_details_enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "edit_username_allowed" {
    null    = false
    type    = boolean
    default = false
  }
  column "otp_policy_counter" {
    null    = true
    type    = integer
    default = 0
  }
  column "otp_policy_window" {
    null    = true
    type    = integer
    default = 1
  }
  column "otp_policy_period" {
    null    = true
    type    = integer
    default = 30
  }
  column "otp_policy_digits" {
    null    = true
    type    = integer
    default = 6
  }
  column "otp_policy_alg" {
    null    = true
    type    = character_varying(36)
    default = "HmacSHA1"
  }
  column "otp_policy_type" {
    null    = true
    type    = character_varying(36)
    default = "totp"
  }
  column "browser_flow" {
    null = true
    type = character_varying(36)
  }
  column "registration_flow" {
    null = true
    type = character_varying(36)
  }
  column "direct_grant_flow" {
    null = true
    type = character_varying(36)
  }
  column "reset_credentials_flow" {
    null = true
    type = character_varying(36)
  }
  column "client_auth_flow" {
    null = true
    type = character_varying(36)
  }
  column "offline_session_idle_timeout" {
    null    = true
    type    = integer
    default = 0
  }
  column "revoke_refresh_token" {
    null    = false
    type    = boolean
    default = false
  }
  column "access_token_life_implicit" {
    null    = true
    type    = integer
    default = 0
  }
  column "login_with_email_allowed" {
    null    = false
    type    = boolean
    default = true
  }
  column "duplicate_emails_allowed" {
    null    = false
    type    = boolean
    default = false
  }
  column "docker_auth_flow" {
    null = true
    type = character_varying(36)
  }
  column "refresh_token_max_reuse" {
    null    = true
    type    = integer
    default = 0
  }
  column "allow_user_managed_access" {
    null    = false
    type    = boolean
    default = false
  }
  column "sso_max_lifespan_remember_me" {
    null    = false
    type    = integer
    default = 0
  }
  column "sso_idle_timeout_remember_me" {
    null    = false
    type    = integer
    default = 0
  }
  column "default_role" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_realm_master_adm_cli" {
    columns = [column.master_admin_client]
  }
  unique "uk_orvsdmla56612eaefiq6wl5oi" {
    columns = [column.name]
  }
}
table "realm_attribute" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.name, column.realm_id]
  }
  foreign_key "fk_8shxd6l3e9atqukacxgpffptw" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_realm_attr_realm" {
    columns = [column.realm_id]
  }
}
table "realm_default_groups" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "group_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.realm_id, column.group_id]
  }
  foreign_key "fk_def_groups_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_realm_def_grp_realm" {
    columns = [column.realm_id]
  }
  unique "con_group_id_def_groups" {
    columns = [column.group_id]
  }
}
table "realm_enabled_event_types" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.realm_id, column.value]
  }
  foreign_key "fk_h846o4h0w8epx5nwedrf5y69j" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_realm_evt_types_realm" {
    columns = [column.realm_id]
  }
}
table "realm_events_listeners" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.realm_id, column.value]
  }
  foreign_key "fk_h846o4h0w8epx5nxev9f5y69j" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_realm_evt_list_realm" {
    columns = [column.realm_id]
  }
}
table "realm_localizations" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(255)
  }
  column "locale" {
    null = false
    type = character_varying(255)
  }
  column "texts" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.realm_id, column.locale]
  }
}
table "realm_required_credential" {
  schema = schema.public
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "form_label" {
    null = true
    type = character_varying(255)
  }
  column "input" {
    null    = false
    type    = boolean
    default = false
  }
  column "secret" {
    null    = false
    type    = boolean
    default = false
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.realm_id, column.type]
  }
  foreign_key "fk_5hg65lybevavkqfki3kponh9v" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "realm_smtp_config" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.realm_id, column.name]
  }
  foreign_key "fk_70ej8xdxgxd0b9hh6180irr0o" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "realm_supported_locales" {
  schema = schema.public
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.realm_id, column.value]
  }
  foreign_key "fk_supported_locales_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_realm_supp_local_realm" {
    columns = [column.realm_id]
  }
}
table "redirect_uris" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.client_id, column.value]
  }
  foreign_key "fk_1burs8pb4ouj97h5wuppahv9f" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_redir_uri_client" {
    columns = [column.client_id]
  }
}
table "required_action_config" {
  schema = schema.public
  column "required_action_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = text
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.required_action_id, column.name]
  }
}
table "required_action_provider" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "alias" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "default_action" {
    null    = false
    type    = boolean
    default = false
  }
  column "provider_id" {
    null = true
    type = character_varying(255)
  }
  column "priority" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_req_act_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_req_act_prov_realm" {
    columns = [column.realm_id]
  }
}
table "resource_attribute" {
  schema = schema.public
  column "id" {
    null    = false
    type    = character_varying(36)
    default = "sybase-needs-something-here"
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "resource_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_5hrm2vlf9ql5fu022kqepovbr" {
    columns     = [column.resource_id]
    ref_columns = [table.resource_server_resource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "resource_policy" {
  schema = schema.public
  column "resource_id" {
    null = false
    type = character_varying(36)
  }
  column "policy_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.resource_id, column.policy_id]
  }
  foreign_key "fk_frsrpos53xcx4wnkog82ssrfy" {
    columns     = [column.resource_id]
    ref_columns = [table.resource_server_resource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrpp213xcx4wnkog82ssrfy" {
    columns     = [column.policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_res_policy_policy" {
    columns = [column.policy_id]
  }
}
table "resource_scope" {
  schema = schema.public
  column "resource_id" {
    null = false
    type = character_varying(36)
  }
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.resource_id, column.scope_id]
  }
  foreign_key "fk_frsrpos13xcx4wnkog82ssrfy" {
    columns     = [column.resource_id]
    ref_columns = [table.resource_server_resource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrps213xcx4wnkog82ssrfy" {
    columns     = [column.scope_id]
    ref_columns = [table.resource_server_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_res_scope_scope" {
    columns = [column.scope_id]
  }
}
table "resource_server" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "allow_rs_remote_mgmt" {
    null    = false
    type    = boolean
    default = false
  }
  column "policy_enforce_mode" {
    null = false
    type = smallint
  }
  column "decision_strategy" {
    null    = false
    type    = smallint
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
}
table "resource_server_perm_ticket" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "owner" {
    null = false
    type = character_varying(255)
  }
  column "requester" {
    null = false
    type = character_varying(255)
  }
  column "created_timestamp" {
    null = false
    type = bigint
  }
  column "granted_timestamp" {
    null = true
    type = bigint
  }
  column "resource_id" {
    null = false
    type = character_varying(36)
  }
  column "scope_id" {
    null = true
    type = character_varying(36)
  }
  column "resource_server_id" {
    null = false
    type = character_varying(36)
  }
  column "policy_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_frsrho213xcx4wnkog82sspmt" {
    columns     = [column.resource_server_id]
    ref_columns = [table.resource_server.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrho213xcx4wnkog83sspmt" {
    columns     = [column.resource_id]
    ref_columns = [table.resource_server_resource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrho213xcx4wnkog84sspmt" {
    columns     = [column.scope_id]
    ref_columns = [table.resource_server_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrpo2128cx4wnkog82ssrfy" {
    columns     = [column.policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_perm_ticket_owner" {
    columns = [column.owner]
  }
  index "idx_perm_ticket_requester" {
    columns = [column.requester]
  }
  unique "uk_frsr6t700s9v50bu18ws5pmt" {
    columns = [column.owner, column.requester, column.resource_server_id, column.resource_id, column.scope_id]
  }
}
table "resource_server_policy" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "decision_strategy" {
    null = true
    type = smallint
  }
  column "logic" {
    null = true
    type = smallint
  }
  column "resource_server_id" {
    null = false
    type = character_varying(36)
  }
  column "owner" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_frsrpo213xcx4wnkog82ssrfy" {
    columns     = [column.resource_server_id]
    ref_columns = [table.resource_server.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_res_serv_pol_res_serv" {
    columns = [column.resource_server_id]
  }
  unique "uk_frsrpt700s9v50bu18ws5ha6" {
    columns = [column.name, column.resource_server_id]
  }
}
table "resource_server_resource" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = true
    type = character_varying(255)
  }
  column "icon_uri" {
    null = true
    type = character_varying(255)
  }
  column "owner" {
    null = false
    type = character_varying(255)
  }
  column "resource_server_id" {
    null = false
    type = character_varying(36)
  }
  column "owner_managed_access" {
    null    = false
    type    = boolean
    default = false
  }
  column "display_name" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_frsrho213xcx4wnkog82ssrfy" {
    columns     = [column.resource_server_id]
    ref_columns = [table.resource_server.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_res_srv_res_res_srv" {
    columns = [column.resource_server_id]
  }
  unique "uk_frsr6t700s9v50bu18ws5ha6" {
    columns = [column.name, column.owner, column.resource_server_id]
  }
}
table "resource_server_scope" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "icon_uri" {
    null = true
    type = character_varying(255)
  }
  column "resource_server_id" {
    null = false
    type = character_varying(36)
  }
  column "display_name" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_frsrso213xcx4wnkog82ssrfy" {
    columns     = [column.resource_server_id]
    ref_columns = [table.resource_server.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_res_srv_scope_res_srv" {
    columns = [column.resource_server_id]
  }
  unique "uk_frsrst700s9v50bu18ws5ha6" {
    columns = [column.name, column.resource_server_id]
  }
}
table "resource_uris" {
  schema = schema.public
  column "resource_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.resource_id, column.value]
  }
  foreign_key "fk_resource_server_uris" {
    columns     = [column.resource_id]
    ref_columns = [table.resource_server_resource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "revoked_token" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(255)
  }
  column "expire" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_rev_token_on_expire" {
    columns = [column.expire]
  }
}
table "role_attribute" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "role_id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_role_attribute_id" {
    columns     = [column.role_id]
    ref_columns = [table.keycloak_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_role_attribute" {
    columns = [column.role_id]
  }
}
table "scope_mapping" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "role_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.client_id, column.role_id]
  }
  foreign_key "fk_ouse064plmlr732lxjcn1q5f1" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_scope_mapping_role" {
    columns = [column.role_id]
  }
}
table "scope_policy" {
  schema = schema.public
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  column "policy_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.scope_id, column.policy_id]
  }
  foreign_key "fk_frsrasp13xcx4wnkog82ssrfy" {
    columns     = [column.policy_id]
    ref_columns = [table.resource_server_policy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_frsrpass3xcx4wnkog82ssrfy" {
    columns     = [column.scope_id]
    ref_columns = [table.resource_server_scope.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_scope_policy_policy" {
    columns = [column.policy_id]
  }
}
table "server_config" {
  schema = schema.public
  column "server_config_key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = text
  }
  column "version" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.server_config_key]
  }
}
table "user_attribute" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  column "id" {
    null    = false
    type    = character_varying(36)
    default = "sybase-needs-something-here"
  }
  column "long_value_hash" {
    null = true
    type = bytea
  }
  column "long_value_hash_lower_case" {
    null = true
    type = bytea
  }
  column "long_value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_5hrm2vlf9ql5fu043kqepovbr" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_attribute" {
    columns = [column.user_id]
  }
  index "idx_user_attribute_name" {
    columns = [column.name, column.value]
  }
  index "user_attr_long_values" {
    columns = [column.long_value_hash, column.name]
  }
  index "user_attr_long_values_lower_case" {
    columns = [column.long_value_hash_lower_case, column.name]
  }
}
table "user_consent" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "client_id" {
    null = true
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  column "created_date" {
    null = true
    type = bigint
  }
  column "last_updated_date" {
    null = true
    type = bigint
  }
  column "client_storage_provider" {
    null = true
    type = character_varying(36)
  }
  column "external_client_id" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_grntcsnt_user" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_consent" {
    columns = [column.user_id]
  }
  unique "uk_external_consent" {
    columns = [column.client_storage_provider, column.external_client_id, column.user_id]
  }
  unique "uk_local_consent" {
    columns = [column.client_id, column.user_id]
  }
}
table "user_consent_client_scope" {
  schema = schema.public
  column "user_consent_id" {
    null = false
    type = character_varying(36)
  }
  column "scope_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.user_consent_id, column.scope_id]
  }
  foreign_key "fk_grntcsnt_clsc_usc" {
    columns     = [column.user_consent_id]
    ref_columns = [table.user_consent.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_usconsent_clscope" {
    columns = [column.user_consent_id]
  }
  index "idx_usconsent_scope_id" {
    columns = [column.scope_id]
  }
}
table "user_entity" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "email_constraint" {
    null = true
    type = character_varying(255)
  }
  column "email_verified" {
    null    = false
    type    = boolean
    default = false
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "federation_link" {
    null = true
    type = character_varying(255)
  }
  column "first_name" {
    null = true
    type = character_varying(255)
  }
  column "last_name" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(255)
  }
  column "username" {
    null = true
    type = character_varying(255)
  }
  column "created_timestamp" {
    null = true
    type = bigint
  }
  column "service_account_client_link" {
    null = true
    type = character_varying(255)
  }
  column "not_before" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_user_email" {
    columns = [column.email]
  }
  index "idx_user_service_account" {
    columns = [column.realm_id, column.service_account_client_link]
  }
  unique "uk_dykn684sl8up1crfei6eckhd7" {
    columns = [column.realm_id, column.email_constraint]
  }
  unique "uk_ru8tt6t700s9v50bu18ws5ha6" {
    columns = [column.realm_id, column.username]
  }
}
table "user_federation_config" {
  schema = schema.public
  column "user_federation_provider_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.user_federation_provider_id, column.name]
  }
  foreign_key "fk_t13hpu1j94r2ebpekr39x5eu5" {
    columns     = [column.user_federation_provider_id]
    ref_columns = [table.user_federation_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "user_federation_mapper" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "federation_provider_id" {
    null = false
    type = character_varying(36)
  }
  column "federation_mapper_type" {
    null = false
    type = character_varying(255)
  }
  column "realm_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_fedmapperpm_fedprv" {
    columns     = [column.federation_provider_id]
    ref_columns = [table.user_federation_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "fk_fedmapperpm_realm" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_usr_fed_map_fed_prv" {
    columns = [column.federation_provider_id]
  }
  index "idx_usr_fed_map_realm" {
    columns = [column.realm_id]
  }
}
table "user_federation_mapper_config" {
  schema = schema.public
  column "user_federation_mapper_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.user_federation_mapper_id, column.name]
  }
  foreign_key "fk_fedmapper_cfg" {
    columns     = [column.user_federation_mapper_id]
    ref_columns = [table.user_federation_mapper.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "user_federation_provider" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "changed_sync_period" {
    null = true
    type = integer
  }
  column "display_name" {
    null = true
    type = character_varying(255)
  }
  column "full_sync_period" {
    null = true
    type = integer
  }
  column "last_sync" {
    null = true
    type = integer
  }
  column "priority" {
    null = true
    type = integer
  }
  column "provider_name" {
    null = true
    type = character_varying(255)
  }
  column "realm_id" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_1fj32f6ptolw2qy60cd8n01e8" {
    columns     = [column.realm_id]
    ref_columns = [table.realm.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_usr_fed_prv_realm" {
    columns = [column.realm_id]
  }
}
table "user_group_membership" {
  schema = schema.public
  column "group_id" {
    null = false
    type = character_varying(36)
  }
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  column "membership_type" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.group_id, column.user_id]
  }
  foreign_key "fk_user_group_user" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_group_mapping" {
    columns = [column.user_id]
  }
}
table "user_required_action" {
  schema = schema.public
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  column "required_action" {
    null    = false
    type    = character_varying(255)
    default = " "
  }
  primary_key {
    columns = [column.required_action, column.user_id]
  }
  foreign_key "fk_6qj3w1jw9cvafhe19bwsiuvmd" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_reqactions" {
    columns = [column.user_id]
  }
}
table "user_role_mapping" {
  schema = schema.public
  column "role_id" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.role_id, column.user_id]
  }
  foreign_key "fk_c4fqv34p1mbylloxang7b1q3l" {
    columns     = [column.user_id]
    ref_columns = [table.user_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_user_role_mapping" {
    columns = [column.user_id]
  }
}
table "web_origins" {
  schema = schema.public
  column "client_id" {
    null = false
    type = character_varying(36)
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.client_id, column.value]
  }
  foreign_key "fk_lojpho213xcx4wnkog82ssrfy" {
    columns     = [column.client_id]
    ref_columns = [table.client.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "idx_web_orig_client" {
    columns = [column.client_id]
  }
}
table "workflow_state" {
  schema = schema.public
  column "execution_id" {
    null = false
    type = character_varying(255)
  }
  column "resource_id" {
    null = false
    type = character_varying(255)
  }
  column "workflow_id" {
    null = false
    type = character_varying(255)
  }
  column "resource_type" {
    null = true
    type = character_varying(255)
  }
  column "scheduled_step_id" {
    null = true
    type = character_varying(255)
  }
  column "scheduled_step_timestamp" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.execution_id]
  }
  index "idx_workflow_state_provider" {
    columns = [column.resource_id]
  }
  index "idx_workflow_state_step" {
    columns = [column.workflow_id, column.scheduled_step_id]
  }
  unique "uq_workflow_resource" {
    columns = [column.workflow_id, column.resource_id]
  }
}
schema "public" {
  comment = "standard public schema"
}
