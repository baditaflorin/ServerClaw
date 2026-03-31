Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "accounts" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "provider_account_id" {
    null = false
    type = character_varying(255)
  }
  column "provider" {
    null = false
    type = character_varying
  }
  column "access_token" {
    null = false
    type = text
  }
  column "access_token_expired_at" {
    null = true
    type = timestamptz
  }
  column "refresh_token" {
    null = true
    type = text
  }
  column "refresh_token_expired_at" {
    null = true
    type = timestamptz
  }
  column "last_connected_at" {
    null = false
    type = timestamptz
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "id_token" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "accounts_user_id_7f1e1f1e_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "accounts_user_id_7f1e1f1e" {
    columns = [column.user_id]
  }
  unique "accounts_provider_provider_account_id_daac1f10_uniq" {
    columns = [column.provider, column.provider_account_id]
  }
}
table "analytic_views" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "query" {
    null = false
    type = jsonb
  }
  column "query_dict" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "analytic_views_created_by_id_1b3ca0a9_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "analytic_views_updated_by_id_b6d827e1_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "analytic_views_workspace_id_ca6e5c0b_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "analytic_views_created_by_id_1b3ca0a9" {
    columns = [column.created_by_id]
  }
  index "analytic_views_updated_by_id_b6d827e1" {
    columns = [column.updated_by_id]
  }
  index "analytic_views_workspace_id_ca6e5c0b" {
    columns = [column.workspace_id]
  }
}
table "api_activity_logs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "token_identifier" {
    null = false
    type = character_varying(255)
  }
  column "path" {
    null = false
    type = character_varying(255)
  }
  column "method" {
    null = false
    type = character_varying(10)
  }
  column "query_params" {
    null = true
    type = text
  }
  column "headers" {
    null = true
    type = text
  }
  column "body" {
    null = true
    type = text
  }
  column "response_code" {
    null = false
    type = integer
  }
  column "response_body" {
    null = true
    type = text
  }
  column "ip_address" {
    null = true
    type = inet
  }
  column "user_agent" {
    null = true
    type = character_varying(512)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "api_activity_logs_created_by_id_7f5c4ca8_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "api_activity_logs_updated_by_id_9ba0d417_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "api_activity_logs_created_by_id_7f5c4ca8" {
    columns = [column.created_by_id]
  }
  index "api_activity_logs_updated_by_id_9ba0d417" {
    columns = [column.updated_by_id]
  }
  check "api_activity_logs_response_code_check" {
    expr = "(response_code >= 0)"
  }
}
table "api_tokens" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "label" {
    null = false
    type = character_varying(255)
  }
  column "user_type" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = true
    type = uuid
  }
  column "description" {
    null = false
    type = text
  }
  column "expired_at" {
    null = true
    type = timestamptz
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "last_used" {
    null = true
    type = timestamptz
  }
  column "is_service" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "api_tokens_created_by_id_441e3d24_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "api_tokens_updated_by_id_bcd544cf_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "api_tokens_user_id_2db24e1c_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "api_tokens_workspace_id_6791c7bd_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "api_tokens_created_by_id_441e3d24" {
    columns = [column.created_by_id]
  }
  index "api_tokens_token_6211101f_like" {
    on {
      column = column.token
      ops    = varchar_pattern_ops
    }
  }
  index "api_tokens_updated_by_id_bcd544cf" {
    columns = [column.updated_by_id]
  }
  index "api_tokens_user_id_2db24e1c" {
    columns = [column.user_id]
  }
  index "api_tokens_workspace_id_6791c7bd" {
    columns = [column.workspace_id]
  }
  check "api_tokens_user_type_check" {
    expr = "(user_type >= 0)"
  }
  unique "api_tokens_token_key" {
    columns = [column.token]
  }
}
table "auth_group" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(150)
  }
  primary_key {
    columns = [column.id]
  }
  index "auth_group_name_a6ea08ec_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  unique "auth_group_name_key" {
    columns = [column.name]
  }
}
table "auth_group_permissions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "group_id" {
    null = false
    type = integer
  }
  column "permission_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "auth_group_permissio_permission_id_84c5c92e_fk_auth_perm" {
    columns     = [column.permission_id]
    ref_columns = [table.auth_permission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "auth_group_permissions_group_id_b120cbf9_fk_auth_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.auth_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "auth_group_permissions_group_id_b120cbf9" {
    columns = [column.group_id]
  }
  index "auth_group_permissions_permission_id_84c5c92e" {
    columns = [column.permission_id]
  }
  unique "auth_group_permissions_group_id_permission_id_0cd325b0_uniq" {
    columns = [column.group_id, column.permission_id]
  }
}
table "auth_permission" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "content_type_id" {
    null = false
    type = integer
  }
  column "codename" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "auth_permission_content_type_id_2f476e4b_fk_django_co" {
    columns     = [column.content_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "auth_permission_content_type_id_2f476e4b" {
    columns = [column.content_type_id]
  }
  unique "auth_permission_content_type_id_codename_01ab375a_uniq" {
    columns = [column.content_type_id, column.codename]
  }
}
table "changelogs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "tags" {
    null = false
    type = jsonb
  }
  column "release_date" {
    null = true
    type = timestamptz
  }
  column "is_release_candidate" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "changelogs_created_by_id_16dd944a_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "changelogs_updated_by_id_e0989861_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "changelogs_created_by_id_16dd944a" {
    columns = [column.created_by_id]
  }
  index "changelogs_updated_by_id_e0989861" {
    columns = [column.updated_by_id]
  }
}
table "comment_reactions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "reaction" {
    null = false
    type = text
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "comment_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "comment_reactions_actor_id_21219e9c_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "comment_reactions_comment_id_87c59446_fk_issue_comments_id" {
    columns     = [column.comment_id]
    ref_columns = [table.issue_comments.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "comment_reactions_created_by_id_9aeb43c4_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "comment_reactions_project_id_ab9114b4_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "comment_reactions_updated_by_id_c74c9bbd_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "comment_reactions_workspace_id_b614ca4f_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "comment_reaction_unique_comment_actor_reaction_when_deleted_at_" {
    unique  = true
    columns = [column.comment_id, column.actor_id, column.reaction]
    where   = "(deleted_at IS NULL)"
  }
  index "comment_reactions_actor_id_21219e9c" {
    columns = [column.actor_id]
  }
  index "comment_reactions_comment_id_87c59446" {
    columns = [column.comment_id]
  }
  index "comment_reactions_created_by_id_9aeb43c4" {
    columns = [column.created_by_id]
  }
  index "comment_reactions_project_id_ab9114b4" {
    columns = [column.project_id]
  }
  index "comment_reactions_updated_by_id_c74c9bbd" {
    columns = [column.updated_by_id]
  }
  index "comment_reactions_workspace_id_b614ca4f" {
    columns = [column.workspace_id]
  }
  unique "comment_reactions_comment_id_actor_id_reac_24dc2de6_uniq" {
    columns = [column.comment_id, column.actor_id, column.reaction, column.deleted_at]
  }
}
table "cycle_issues" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "cycle_id" {
    null = false
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "cycle_issue_created_by_id_30b27539_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_issue_cycle_id_ec681215_fk_cycle_id" {
    columns     = [column.cycle_id]
    ref_columns = [table.cycles.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_issue_project_id_6ad3257a_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_issue_updated_by_id_cb4516f2_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_issue_workspace_id_1d77330e_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_issues_issue_id_2d5ac97f_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "cycle_issue_created_by_id_30b27539" {
    columns = [column.created_by_id]
  }
  index "cycle_issue_cycle_id_ec681215" {
    columns = [column.cycle_id]
  }
  index "cycle_issue_project_id_6ad3257a" {
    columns = [column.project_id]
  }
  index "cycle_issue_updated_by_id_cb4516f2" {
    columns = [column.updated_by_id]
  }
  index "cycle_issue_when_deleted_at_null" {
    unique  = true
    columns = [column.cycle_id, column.issue_id]
    where   = "(deleted_at IS NULL)"
  }
  index "cycle_issue_workspace_id_1d77330e" {
    columns = [column.workspace_id]
  }
  index "cycle_issues_issue_id_2d5ac97f" {
    columns = [column.issue_id]
  }
  unique "cycle_issues_issue_id_cycle_id_deleted_at_93e8fecd_uniq" {
    columns = [column.issue_id, column.cycle_id, column.deleted_at]
  }
}
table "cycle_user_properties" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "display_filters" {
    null = false
    type = jsonb
  }
  column "display_properties" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "cycle_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "cycle_user_properties_created_by_id_501f371c_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_user_properties_cycle_id_1f8bdf35_fk_cycles_id" {
    columns     = [column.cycle_id]
    ref_columns = [table.cycles.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_user_properties_project_id_4efc0f07_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_user_properties_updated_by_id_1b5ac27b_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_user_properties_user_id_9e9ef97d_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_user_properties_workspace_id_62d65d71_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "cycle_user_properties_created_by_id_501f371c" {
    columns = [column.created_by_id]
  }
  index "cycle_user_properties_cycle_id_1f8bdf35" {
    columns = [column.cycle_id]
  }
  index "cycle_user_properties_project_id_4efc0f07" {
    columns = [column.project_id]
  }
  index "cycle_user_properties_unique_cycle_user_when_deleted_at_null" {
    unique  = true
    columns = [column.cycle_id, column.user_id]
    where   = "(deleted_at IS NULL)"
  }
  index "cycle_user_properties_updated_by_id_1b5ac27b" {
    columns = [column.updated_by_id]
  }
  index "cycle_user_properties_user_id_9e9ef97d" {
    columns = [column.user_id]
  }
  index "cycle_user_properties_workspace_id_62d65d71" {
    columns = [column.workspace_id]
  }
  unique "cycle_user_properties_cycle_id_user_id_deleted_at_fbe00cf4_uniq" {
    columns = [column.cycle_id, column.user_id, column.deleted_at]
  }
}
table "cycles" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "start_date" {
    null = true
    type = timestamptz
  }
  column "end_date" {
    null = true
    type = timestamptz
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "progress_snapshot" {
    null = false
    type = jsonb
  }
  column "archived_at" {
    null = true
    type = timestamptz
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "timezone" {
    null = false
    type = character_varying(255)
  }
  column "version" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "cycle_created_by_id_78e43b79_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_owned_by_id_5456a4d1_fk_user_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_project_id_0b590349_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_updated_by_id_93baee43_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "cycle_workspace_id_a199e8e1_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "cycle_created_by_id_78e43b79" {
    columns = [column.created_by_id]
  }
  index "cycle_owned_by_id_5456a4d1" {
    columns = [column.owned_by_id]
  }
  index "cycle_project_id_0b590349" {
    columns = [column.project_id]
  }
  index "cycle_updated_by_id_93baee43" {
    columns = [column.updated_by_id]
  }
  index "cycle_workspace_id_a199e8e1" {
    columns = [column.workspace_id]
  }
}
table "deploy_boards" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "entity_name" {
    null = true
    type = character_varying(30)
  }
  column "anchor" {
    null = false
    type = character_varying(255)
  }
  column "is_comments_enabled" {
    null = false
    type = boolean
  }
  column "is_reactions_enabled" {
    null = false
    type = boolean
  }
  column "is_votes_enabled" {
    null = false
    type = boolean
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "intake_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "is_activity_enabled" {
    null = false
    type = boolean
  }
  column "is_disabled" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "deploy_boards_created_by_id_149dff93_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "deploy_boards_intake_id_76a6470a_fk_intakes_id" {
    columns     = [column.intake_id]
    ref_columns = [table.intakes.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "deploy_boards_project_id_cfc792a1_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "deploy_boards_updated_by_id_db7ae24f_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "deploy_boards_workspace_id_fcf03158_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "deploy_board_unique_entity_name_entity_identifier_when_deleted_" {
    unique  = true
    columns = [column.entity_name, column.entity_identifier]
    where   = "(deleted_at IS NULL)"
  }
  index "deploy_boards_anchor_fe87f323_like" {
    on {
      column = column.anchor
      ops    = varchar_pattern_ops
    }
  }
  index "deploy_boards_created_by_id_149dff93" {
    columns = [column.created_by_id]
  }
  index "deploy_boards_inbox_id_ebc13d44" {
    columns = [column.intake_id]
  }
  index "deploy_boards_project_id_cfc792a1" {
    columns = [column.project_id]
  }
  index "deploy_boards_updated_by_id_db7ae24f" {
    columns = [column.updated_by_id]
  }
  index "deploy_boards_workspace_id_fcf03158" {
    columns = [column.workspace_id]
  }
  unique "deploy_boards_anchor_key" {
    columns = [column.anchor]
  }
  unique "deploy_boards_entity_name_entity_ident_800ce160_uniq" {
    columns = [column.entity_name, column.entity_identifier, column.deleted_at]
  }
}
table "description_versions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "description_json" {
    null = false
    type = jsonb
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "description_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "description_versions_created_by_id_6633a3de_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "description_versions_description_id_dc7f19b6_fk_descriptions_id" {
    columns     = [column.description_id]
    ref_columns = [table.descriptions.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "description_versions_project_id_1a6c9aa9_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "description_versions_updated_by_id_8b5179ae_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "description_versions_workspace_id_52857186_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "description_versions_created_by_id_6633a3de" {
    columns = [column.created_by_id]
  }
  index "description_versions_description_id_dc7f19b6" {
    columns = [column.description_id]
  }
  index "description_versions_project_id_1a6c9aa9" {
    columns = [column.project_id]
  }
  index "description_versions_updated_by_id_8b5179ae" {
    columns = [column.updated_by_id]
  }
  index "description_versions_workspace_id_52857186" {
    columns = [column.workspace_id]
  }
}
table "descriptions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "description_json" {
    null = false
    type = jsonb
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "descriptions_created_by_id_b88ab399_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "descriptions_project_id_8f46180b_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "descriptions_updated_by_id_af519c4d_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "descriptions_workspace_id_767279bf_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "descriptions_created_by_id_b88ab399" {
    columns = [column.created_by_id]
  }
  index "descriptions_project_id_8f46180b" {
    columns = [column.project_id]
  }
  index "descriptions_updated_by_id_af519c4d" {
    columns = [column.updated_by_id]
  }
  index "descriptions_workspace_id_767279bf" {
    columns = [column.workspace_id]
  }
}
table "device_sessions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "user_agent" {
    null = true
    type = character_varying(255)
  }
  column "ip_address" {
    null = true
    type = inet
  }
  column "start_time" {
    null = false
    type = timestamptz
  }
  column "end_time" {
    null = true
    type = timestamptz
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "device_id" {
    null = false
    type = uuid
  }
  column "session_id" {
    null = false
    type = character_varying(128)
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "device_sessions_created_by_id_920a3bd5_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "device_sessions_device_id_a42b2ada_fk_devices_id" {
    columns     = [column.device_id]
    ref_columns = [table.devices.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "device_sessions_session_id_5382b02b_fk_sessions_session_key" {
    columns     = [column.session_id]
    ref_columns = [table.sessions.column.session_key]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "device_sessions_updated_by_id_d0bd0c76_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "device_sessions_created_by_id_920a3bd5" {
    columns = [column.created_by_id]
  }
  index "device_sessions_device_id_a42b2ada" {
    columns = [column.device_id]
  }
  index "device_sessions_session_id_5382b02b" {
    columns = [column.session_id]
  }
  index "device_sessions_session_id_5382b02b_like" {
    on {
      column = column.session_id
      ops    = varchar_pattern_ops
    }
  }
  index "device_sessions_updated_by_id_d0bd0c76" {
    columns = [column.updated_by_id]
  }
}
table "devices" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "device_id" {
    null = true
    type = character_varying(255)
  }
  column "device_type" {
    null = false
    type = character_varying(255)
  }
  column "push_token" {
    null = true
    type = character_varying(255)
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "devices_created_by_id_410a755b_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "devices_updated_by_id_ee20dc3c_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "devices_user_id_9a5cca49_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "devices_created_by_id_410a755b" {
    columns = [column.created_by_id]
  }
  index "devices_updated_by_id_ee20dc3c" {
    columns = [column.updated_by_id]
  }
  index "devices_user_id_9a5cca49" {
    columns = [column.user_id]
  }
}
table "django_celery_beat_clockedschedule" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "clocked_time" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
}
table "django_celery_beat_crontabschedule" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "minute" {
    null = false
    type = character_varying(240)
  }
  column "hour" {
    null = false
    type = character_varying(96)
  }
  column "day_of_week" {
    null = false
    type = character_varying(64)
  }
  column "day_of_month" {
    null = false
    type = character_varying(124)
  }
  column "month_of_year" {
    null = false
    type = character_varying(64)
  }
  column "timezone" {
    null = false
    type = character_varying(63)
  }
  primary_key {
    columns = [column.id]
  }
}
table "django_celery_beat_intervalschedule" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "every" {
    null = false
    type = integer
  }
  column "period" {
    null = false
    type = character_varying(24)
  }
  primary_key {
    columns = [column.id]
  }
}
table "django_celery_beat_periodictask" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "task" {
    null = false
    type = character_varying(200)
  }
  column "args" {
    null = false
    type = text
  }
  column "kwargs" {
    null = false
    type = text
  }
  column "queue" {
    null = true
    type = character_varying(200)
  }
  column "exchange" {
    null = true
    type = character_varying(200)
  }
  column "routing_key" {
    null = true
    type = character_varying(200)
  }
  column "expires" {
    null = true
    type = timestamptz
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "last_run_at" {
    null = true
    type = timestamptz
  }
  column "total_run_count" {
    null = false
    type = integer
  }
  column "date_changed" {
    null = false
    type = timestamptz
  }
  column "description" {
    null = false
    type = text
  }
  column "crontab_id" {
    null = true
    type = integer
  }
  column "interval_id" {
    null = true
    type = integer
  }
  column "solar_id" {
    null = true
    type = integer
  }
  column "one_off" {
    null = false
    type = boolean
  }
  column "start_time" {
    null = true
    type = timestamptz
  }
  column "priority" {
    null = true
    type = integer
  }
  column "headers" {
    null = false
    type = text
  }
  column "clocked_id" {
    null = true
    type = integer
  }
  column "expire_seconds" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "django_celery_beat_p_clocked_id_47a69f82_fk_django_ce" {
    columns     = [column.clocked_id]
    ref_columns = [table.django_celery_beat_clockedschedule.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "django_celery_beat_p_crontab_id_d3cba168_fk_django_ce" {
    columns     = [column.crontab_id]
    ref_columns = [table.django_celery_beat_crontabschedule.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "django_celery_beat_p_interval_id_a8ca27da_fk_django_ce" {
    columns     = [column.interval_id]
    ref_columns = [table.django_celery_beat_intervalschedule.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "django_celery_beat_p_solar_id_a87ce72c_fk_django_ce" {
    columns     = [column.solar_id]
    ref_columns = [table.django_celery_beat_solarschedule.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "django_celery_beat_periodictask_clocked_id_47a69f82" {
    columns = [column.clocked_id]
  }
  index "django_celery_beat_periodictask_crontab_id_d3cba168" {
    columns = [column.crontab_id]
  }
  index "django_celery_beat_periodictask_interval_id_a8ca27da" {
    columns = [column.interval_id]
  }
  index "django_celery_beat_periodictask_name_265a36b7_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "django_celery_beat_periodictask_solar_id_a87ce72c" {
    columns = [column.solar_id]
  }
  check "django_celery_beat_periodictask_expire_seconds_check" {
    expr = "(expire_seconds >= 0)"
  }
  check "django_celery_beat_periodictask_priority_check" {
    expr = "(priority >= 0)"
  }
  check "django_celery_beat_periodictask_total_run_count_check" {
    expr = "(total_run_count >= 0)"
  }
  unique "django_celery_beat_periodictask_name_key" {
    columns = [column.name]
  }
}
table "django_celery_beat_periodictasks" {
  schema = schema.public
  column "ident" {
    null = false
    type = smallint
  }
  column "last_update" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.ident]
  }
}
table "django_celery_beat_solarschedule" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "event" {
    null = false
    type = character_varying(24)
  }
  column "latitude" {
    null = false
    type = numeric(9,6)
  }
  column "longitude" {
    null = false
    type = numeric(9,6)
  }
  primary_key {
    columns = [column.id]
  }
  unique "django_celery_beat_solar_event_latitude_longitude_ba64999a_uniq" {
    columns = [column.event, column.latitude, column.longitude]
  }
}
table "django_content_type" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "app_label" {
    null = false
    type = character_varying(100)
  }
  column "model" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  unique "django_content_type_app_label_model_76bd3d3b_uniq" {
    columns = [column.app_label, column.model]
  }
}
table "django_migrations" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "app" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "applied" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
}
table "django_session" {
  schema = schema.public
  column "session_key" {
    null = false
    type = character_varying(40)
  }
  column "session_data" {
    null = false
    type = text
  }
  column "expire_date" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.session_key]
  }
  index "django_session_expire_date_a5c62663" {
    columns = [column.expire_date]
  }
  index "django_session_session_key_c0390e0f_like" {
    on {
      column = column.session_key
      ops    = varchar_pattern_ops
    }
  }
}
table "draft_issue_assignees" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "assignee_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "draft_issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "draft_issue_assignee_draft_issue_id_70827be2_fk_draft_iss" {
    columns     = [column.draft_issue_id]
    ref_columns = [table.draft_issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_assignees_assignee_id_9cc52f9d_fk_users_id" {
    columns     = [column.assignee_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_assignees_created_by_id_c25d4bde_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_assignees_project_id_c87dd571_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_assignees_updated_by_id_16dbb5e0_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_assignees_workspace_id_e28a98e9_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "draft_issue_assignee_unique_issue_assignee_when_deleted_at_null" {
    unique  = true
    columns = [column.draft_issue_id, column.assignee_id]
    where   = "(deleted_at IS NULL)"
  }
  index "draft_issue_assignees_assignee_id_9cc52f9d" {
    columns = [column.assignee_id]
  }
  index "draft_issue_assignees_created_by_id_c25d4bde" {
    columns = [column.created_by_id]
  }
  index "draft_issue_assignees_draft_issue_id_70827be2" {
    columns = [column.draft_issue_id]
  }
  index "draft_issue_assignees_project_id_c87dd571" {
    columns = [column.project_id]
  }
  index "draft_issue_assignees_updated_by_id_16dbb5e0" {
    columns = [column.updated_by_id]
  }
  index "draft_issue_assignees_workspace_id_e28a98e9" {
    columns = [column.workspace_id]
  }
  unique "draft_issue_assignees_draft_issue_id_assignee__7cd49721_uniq" {
    columns = [column.draft_issue_id, column.assignee_id, column.deleted_at]
  }
}
table "draft_issue_cycles" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "cycle_id" {
    null = false
    type = uuid
  }
  column "draft_issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "draft_issue_cycles_created_by_id_e56335c8_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_cycles_cycle_id_b214e11f_fk_cycles_id" {
    columns     = [column.cycle_id]
    ref_columns = [table.cycles.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_cycles_draft_issue_id_ed45e8a2_fk_draft_issues_id" {
    columns     = [column.draft_issue_id]
    ref_columns = [table.draft_issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_cycles_project_id_dc5d1ff6_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_cycles_updated_by_id_518a23ab_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_cycles_workspace_id_4fd0aa0c_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "draft_issue_cycle_when_deleted_at_null" {
    unique  = true
    columns = [column.draft_issue_id, column.cycle_id]
    where   = "(deleted_at IS NULL)"
  }
  index "draft_issue_cycles_created_by_id_e56335c8" {
    columns = [column.created_by_id]
  }
  index "draft_issue_cycles_cycle_id_b214e11f" {
    columns = [column.cycle_id]
  }
  index "draft_issue_cycles_draft_issue_id_ed45e8a2" {
    columns = [column.draft_issue_id]
  }
  index "draft_issue_cycles_project_id_dc5d1ff6" {
    columns = [column.project_id]
  }
  index "draft_issue_cycles_updated_by_id_518a23ab" {
    columns = [column.updated_by_id]
  }
  index "draft_issue_cycles_workspace_id_4fd0aa0c" {
    columns = [column.workspace_id]
  }
  unique "draft_issue_cycles_draft_issue_id_cycle_id__e133e097_uniq" {
    columns = [column.draft_issue_id, column.cycle_id, column.deleted_at]
  }
}
table "draft_issue_labels" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "draft_issue_id" {
    null = false
    type = uuid
  }
  column "label_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "draft_issue_labels_created_by_id_88217eef_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_labels_draft_issue_id_339d4c2b_fk_draft_issues_id" {
    columns     = [column.draft_issue_id]
    ref_columns = [table.draft_issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_labels_label_id_b9b001a5_fk_labels_id" {
    columns     = [column.label_id]
    ref_columns = [table.labels.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_labels_project_id_16f9ba0a_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_labels_updated_by_id_edac537c_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_labels_workspace_id_489a9873_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "draft_issue_labels_created_by_id_88217eef" {
    columns = [column.created_by_id]
  }
  index "draft_issue_labels_draft_issue_id_339d4c2b" {
    columns = [column.draft_issue_id]
  }
  index "draft_issue_labels_label_id_b9b001a5" {
    columns = [column.label_id]
  }
  index "draft_issue_labels_project_id_16f9ba0a" {
    columns = [column.project_id]
  }
  index "draft_issue_labels_updated_by_id_edac537c" {
    columns = [column.updated_by_id]
  }
  index "draft_issue_labels_workspace_id_489a9873" {
    columns = [column.workspace_id]
  }
}
table "draft_issue_modules" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "draft_issue_id" {
    null = false
    type = uuid
  }
  column "module_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "draft_issue_modules_created_by_id_95ec4247_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_modules_draft_issue_id_eb470383_fk_draft_issues_id" {
    columns     = [column.draft_issue_id]
    ref_columns = [table.draft_issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_modules_module_id_4d3f477a_fk_modules_id" {
    columns     = [column.module_id]
    ref_columns = [table.modules.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_modules_project_id_c32eadab_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_modules_updated_by_id_18548965_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issue_modules_workspace_id_536c335a_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "draft_issue_modules_created_by_id_95ec4247" {
    columns = [column.created_by_id]
  }
  index "draft_issue_modules_draft_issue_id_eb470383" {
    columns = [column.draft_issue_id]
  }
  index "draft_issue_modules_module_id_4d3f477a" {
    columns = [column.module_id]
  }
  index "draft_issue_modules_project_id_c32eadab" {
    columns = [column.project_id]
  }
  index "draft_issue_modules_updated_by_id_18548965" {
    columns = [column.updated_by_id]
  }
  index "draft_issue_modules_workspace_id_536c335a" {
    columns = [column.workspace_id]
  }
  index "module_draft_issue_unique_issue_module_when_deleted_at_null" {
    unique  = true
    columns = [column.draft_issue_id, column.module_id]
    where   = "(deleted_at IS NULL)"
  }
  unique "draft_issue_modules_draft_issue_id_module_id_634e1f1a_uniq" {
    columns = [column.draft_issue_id, column.module_id, column.deleted_at]
  }
}
table "draft_issues" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = jsonb
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "priority" {
    null = false
    type = character_varying(30)
  }
  column "start_date" {
    null = true
    type = date
  }
  column "target_date" {
    null = true
    type = date
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "completed_at" {
    null = true
    type = timestamptz
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "estimate_point_id" {
    null = true
    type = uuid
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "state_id" {
    null = true
    type = uuid
  }
  column "type_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "draft_issues_created_by_id_aedba72a_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_estimate_point_id_9e333189_fk_estimate_points_id" {
    columns     = [column.estimate_point_id]
    ref_columns = [table.estimate_points.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_parent_id_eee6ec32_fk_issues_id" {
    columns     = [column.parent_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_project_id_784a560c_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_state_id_94f28f5a_fk_states_id" {
    columns     = [column.state_id]
    ref_columns = [table.states.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_type_id_7a62fe34_fk_issue_types_id" {
    columns     = [column.type_id]
    ref_columns = [table.issue_types.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_updated_by_id_1ca3cd4e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "draft_issues_workspace_id_9d8512c8_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "draft_issues_created_by_id_aedba72a" {
    columns = [column.created_by_id]
  }
  index "draft_issues_estimate_point_id_9e333189" {
    columns = [column.estimate_point_id]
  }
  index "draft_issues_parent_id_eee6ec32" {
    columns = [column.parent_id]
  }
  index "draft_issues_project_id_784a560c" {
    columns = [column.project_id]
  }
  index "draft_issues_state_id_94f28f5a" {
    columns = [column.state_id]
  }
  index "draft_issues_type_id_7a62fe34" {
    columns = [column.type_id]
  }
  index "draft_issues_updated_by_id_1ca3cd4e" {
    columns = [column.updated_by_id]
  }
  index "draft_issues_workspace_id_9d8512c8" {
    columns = [column.workspace_id]
  }
}
table "email_notification_logs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "entity_name" {
    null = false
    type = character_varying(255)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "processed_at" {
    null = true
    type = timestamptz
  }
  column "sent_at" {
    null = true
    type = timestamptz
  }
  column "entity" {
    null = false
    type = character_varying(200)
  }
  column "old_value" {
    null = true
    type = character_varying(300)
  }
  column "new_value" {
    null = true
    type = character_varying(300)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "receiver_id" {
    null = false
    type = uuid
  }
  column "triggered_by_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "email_notification_logs_created_by_id_6faff587_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "email_notification_logs_receiver_id_7c7d2e13_fk_users_id" {
    columns     = [column.receiver_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "email_notification_logs_triggered_by_id_b551e727_fk_users_id" {
    columns     = [column.triggered_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "email_notification_logs_updated_by_id_5d99c798_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "email_notification_logs_created_by_id_6faff587" {
    columns = [column.created_by_id]
  }
  index "email_notification_logs_receiver_id_7c7d2e13" {
    columns = [column.receiver_id]
  }
  index "email_notification_logs_triggered_by_id_b551e727" {
    columns = [column.triggered_by_id]
  }
  index "email_notification_logs_updated_by_id_5d99c798" {
    columns = [column.updated_by_id]
  }
}
table "estimate_points" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "key" {
    null = false
    type = integer
  }
  column "description" {
    null = false
    type = text
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "estimate_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "estimate_points_created_by_id_d1b04bd9_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimate_points_estimate_id_4b4cb706_fk_estimates_id" {
    columns     = [column.estimate_id]
    ref_columns = [table.estimates.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimate_points_project_id_ba9bcb2c_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimate_points_updated_by_id_a1da94e1_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimate_points_workspace_id_96fc4f92_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "estimate_points_created_by_id_d1b04bd9" {
    columns = [column.created_by_id]
  }
  index "estimate_points_estimate_id_4b4cb706" {
    columns = [column.estimate_id]
  }
  index "estimate_points_project_id_ba9bcb2c" {
    columns = [column.project_id]
  }
  index "estimate_points_updated_by_id_a1da94e1" {
    columns = [column.updated_by_id]
  }
  index "estimate_points_workspace_id_96fc4f92" {
    columns = [column.workspace_id]
  }
}
table "estimates" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "last_used" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "estimates_created_by_id_7e401493_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimates_project_id_7f195a41_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimates_updated_by_id_b3fcfb1d_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "estimates_workspace_id_718811eb_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "estimate_unique_name_project_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.project_id]
    where   = "(deleted_at IS NULL)"
  }
  index "estimates_created_by_id_7e401493" {
    columns = [column.created_by_id]
  }
  index "estimates_project_id_7f195a41" {
    columns = [column.project_id]
  }
  index "estimates_updated_by_id_b3fcfb1d" {
    columns = [column.updated_by_id]
  }
  index "estimates_workspace_id_718811eb" {
    columns = [column.workspace_id]
  }
  unique "estimates_name_project_id_deleted_at_41d66639_uniq" {
    columns = [column.name, column.project_id, column.deleted_at]
  }
}
table "exporters" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "project" {
    null = true
    type = sql("uuid[]")
  }
  column "provider" {
    null = false
    type = character_varying(50)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "reason" {
    null = false
    type = text
  }
  column "key" {
    null = false
    type = text
  }
  column "url" {
    null = true
    type = character_varying(800)
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "initiated_by_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "filters" {
    null = true
    type = jsonb
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "exporters_created_by_id_44e1d9b3_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "exporters_initiated_by_id_d51f7552_fk_users_id" {
    columns     = [column.initiated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "exporters_updated_by_id_d2572861_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "exporters_workspace_id_11a04317_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "exporters_created_by_id_44e1d9b3" {
    columns = [column.created_by_id]
  }
  index "exporters_initiated_by_id_d51f7552" {
    columns = [column.initiated_by_id]
  }
  index "exporters_token_c774aeeb_like" {
    on {
      column = column.token
      ops    = varchar_pattern_ops
    }
  }
  index "exporters_updated_by_id_d2572861" {
    columns = [column.updated_by_id]
  }
  index "exporters_workspace_id_11a04317" {
    columns = [column.workspace_id]
  }
  unique "exporters_token_key" {
    columns = [column.token]
  }
}
table "file_assets" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "attributes" {
    null = false
    type = jsonb
  }
  column "asset" {
    null = false
    type = character_varying(800)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = true
    type = uuid
  }
  column "is_deleted" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "is_archived" {
    null = false
    type = boolean
  }
  column "comment_id" {
    null = true
    type = uuid
  }
  column "entity_type" {
    null = true
    type = character_varying(255)
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "is_uploaded" {
    null = false
    type = boolean
  }
  column "issue_id" {
    null = true
    type = uuid
  }
  column "page_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "size" {
    null = false
    type = double_precision
  }
  column "storage_metadata" {
    null = true
    type = jsonb
  }
  column "user_id" {
    null = true
    type = uuid
  }
  column "draft_issue_id" {
    null = true
    type = uuid
  }
  column "entity_identifier" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "file_asset_created_by_id_966942a0_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_asset_updated_by_id_d6aaf4f0_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_comment_id_35d4ecaf_fk_issue_comments_id" {
    columns     = [column.comment_id]
    ref_columns = [table.issue_comments.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_draft_issue_id_52633145_fk_draft_issues_id" {
    columns     = [column.draft_issue_id]
    ref_columns = [table.draft_issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_issue_id_cfe87d6c_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_page_id_64c753d1_fk_pages_id" {
    columns     = [column.page_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_project_id_ebd5c0d8_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_user_id_ce1818dc_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "file_assets_workspace_id_fa50b9c5_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "asset_asset_idx" {
    columns = [column.asset]
  }
  index "asset_entity_identifier_idx" {
    columns = [column.entity_identifier]
  }
  index "asset_entity_idx" {
    columns = [column.entity_type, column.entity_identifier]
  }
  index "asset_entity_type_idx" {
    columns = [column.entity_type]
  }
  index "file_asset_created_by_id_966942a0" {
    columns = [column.created_by_id]
  }
  index "file_asset_updated_by_id_d6aaf4f0" {
    columns = [column.updated_by_id]
  }
  index "file_assets_comment_id_35d4ecaf" {
    columns = [column.comment_id]
  }
  index "file_assets_draft_issue_id_52633145" {
    columns = [column.draft_issue_id]
  }
  index "file_assets_issue_id_cfe87d6c" {
    columns = [column.issue_id]
  }
  index "file_assets_page_id_64c753d1" {
    columns = [column.page_id]
  }
  index "file_assets_project_id_ebd5c0d8" {
    columns = [column.project_id]
  }
  index "file_assets_user_id_ce1818dc" {
    columns = [column.user_id]
  }
  index "file_assets_workspace_id_fa50b9c5" {
    columns = [column.workspace_id]
  }
}
table "github_comment_syncs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "repo_comment_id" {
    null = false
    type = bigint
  }
  column "comment_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_sync_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "github_comment_syncs_comment_id_6feec6d1_fk_issue_comments_id" {
    columns     = [column.comment_id]
    ref_columns = [table.issue_comments.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_comment_syncs_created_by_id_b1ef2517_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_comment_syncs_issue_sync_id_5e738eb5_fk_github_is" {
    columns     = [column.issue_sync_id]
    ref_columns = [table.github_issue_syncs.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_comment_syncs_project_id_6d199ace_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_comment_syncs_updated_by_id_bb05c066_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_comment_syncs_workspace_id_b54528c8_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "github_comment_syncs_comment_id_6feec6d1" {
    columns = [column.comment_id]
  }
  index "github_comment_syncs_created_by_id_b1ef2517" {
    columns = [column.created_by_id]
  }
  index "github_comment_syncs_issue_sync_id_5e738eb5" {
    columns = [column.issue_sync_id]
  }
  index "github_comment_syncs_project_id_6d199ace" {
    columns = [column.project_id]
  }
  index "github_comment_syncs_updated_by_id_bb05c066" {
    columns = [column.updated_by_id]
  }
  index "github_comment_syncs_workspace_id_b54528c8" {
    columns = [column.workspace_id]
  }
  unique "github_comment_syncs_issue_sync_id_comment_id_38c82e7b_uniq" {
    columns = [column.issue_sync_id, column.comment_id]
  }
}
table "github_issue_syncs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "repo_issue_id" {
    null = false
    type = bigint
  }
  column "github_issue_id" {
    null = false
    type = bigint
  }
  column "issue_url" {
    null = false
    type = character_varying(200)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "repository_sync_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "github_issue_syncs_created_by_id_d02b7c56_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_issue_syncs_issue_id_450cb083_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_issue_syncs_project_id_4609ad0c_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_issue_syncs_repository_sync_id_ba0d4de4_fk_github_re" {
    columns     = [column.repository_sync_id]
    ref_columns = [table.github_repository_syncs.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_issue_syncs_updated_by_id_e9cd6f86_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_issue_syncs_workspace_id_eae020ad_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "github_issue_syncs_created_by_id_d02b7c56" {
    columns = [column.created_by_id]
  }
  index "github_issue_syncs_issue_id_450cb083" {
    columns = [column.issue_id]
  }
  index "github_issue_syncs_project_id_4609ad0c" {
    columns = [column.project_id]
  }
  index "github_issue_syncs_repository_sync_id_ba0d4de4" {
    columns = [column.repository_sync_id]
  }
  index "github_issue_syncs_updated_by_id_e9cd6f86" {
    columns = [column.updated_by_id]
  }
  index "github_issue_syncs_workspace_id_eae020ad" {
    columns = [column.workspace_id]
  }
  unique "github_issue_syncs_repository_sync_id_issue_id_4b34427e_uniq" {
    columns = [column.repository_sync_id, column.issue_id]
  }
}
table "github_repositories" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(500)
  }
  column "url" {
    null = true
    type = character_varying(200)
  }
  column "config" {
    null = false
    type = jsonb
  }
  column "repository_id" {
    null = false
    type = bigint
  }
  column "owner" {
    null = false
    type = character_varying(500)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "github_repositories_created_by_id_104fa685_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repositories_project_id_65c546bb_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repositories_updated_by_id_8aa4d772_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repositories_workspace_id_c4de7326_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "github_repositories_created_by_id_104fa685" {
    columns = [column.created_by_id]
  }
  index "github_repositories_project_id_65c546bb" {
    columns = [column.project_id]
  }
  index "github_repositories_updated_by_id_8aa4d772" {
    columns = [column.updated_by_id]
  }
  index "github_repositories_workspace_id_c4de7326" {
    columns = [column.workspace_id]
  }
}
table "github_repository_syncs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "credentials" {
    null = false
    type = jsonb
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "label_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "repository_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "workspace_integration_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "github_repository_sy_repository_id_ead52404_fk_github_re" {
    columns     = [column.repository_id]
    ref_columns = [table.github_repositories.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_sy_workspace_integratio_62858398_fk_workspace" {
    columns     = [column.workspace_integration_id]
    ref_columns = [table.workspace_integrations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_actor_id_1fa689fe_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_created_by_id_0df94495_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_label_id_eb1e9bd7_fk_labels_id" {
    columns     = [column.label_id]
    ref_columns = [table.labels.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_project_id_e7e8291e_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_updated_by_id_07e9d065_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "github_repository_syncs_workspace_id_4a22a8b8_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "github_repository_syncs_actor_id_1fa689fe" {
    columns = [column.actor_id]
  }
  index "github_repository_syncs_created_by_id_0df94495" {
    columns = [column.created_by_id]
  }
  index "github_repository_syncs_label_id_eb1e9bd7" {
    columns = [column.label_id]
  }
  index "github_repository_syncs_project_id_e7e8291e" {
    columns = [column.project_id]
  }
  index "github_repository_syncs_updated_by_id_07e9d065" {
    columns = [column.updated_by_id]
  }
  index "github_repository_syncs_workspace_id_4a22a8b8" {
    columns = [column.workspace_id]
  }
  index "github_repository_syncs_workspace_integration_id_62858398" {
    columns = [column.workspace_integration_id]
  }
  unique "github_repository_syncs_project_id_repository_id_0f3705e6_uniq" {
    columns = [column.project_id, column.repository_id]
  }
  unique "github_repository_syncs_repository_id_key" {
    columns = [column.repository_id]
  }
}
table "importers" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "service" {
    null = false
    type = character_varying(50)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "config" {
    null = false
    type = jsonb
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "initiated_by_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "token_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "imported_data" {
    null = true
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "importers_created_by_id_7dd06433_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "importers_initiated_by_id_3cddbd23_fk_users_id" {
    columns     = [column.initiated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "importers_project_id_1f8b43ef_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "importers_token_id_c951e89f_fk_api_tokens_id" {
    columns     = [column.token_id]
    ref_columns = [table.api_tokens.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "importers_updated_by_id_3915139e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "importers_workspace_id_795b8985_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "importers_created_by_id_7dd06433" {
    columns = [column.created_by_id]
  }
  index "importers_initiated_by_id_3cddbd23" {
    columns = [column.initiated_by_id]
  }
  index "importers_project_id_1f8b43ef" {
    columns = [column.project_id]
  }
  index "importers_token_id_c951e89f" {
    columns = [column.token_id]
  }
  index "importers_updated_by_id_3915139e" {
    columns = [column.updated_by_id]
  }
  index "importers_workspace_id_795b8985" {
    columns = [column.workspace_id]
  }
}
table "instance_admins" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "role" {
    null = false
    type = integer
  }
  column "is_verified" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "instance_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "instance_admins_created_by_id_7f4e03b4_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "instance_admins_instance_id_66d1ba73_fk_instances_id" {
    columns     = [column.instance_id]
    ref_columns = [table.instances.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "instance_admins_updated_by_id_b7800403_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "instance_admins_user_id_cc6e9b62_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "instance_admins_created_by_id_7f4e03b4" {
    columns = [column.created_by_id]
  }
  index "instance_admins_instance_id_66d1ba73" {
    columns = [column.instance_id]
  }
  index "instance_admins_updated_by_id_b7800403" {
    columns = [column.updated_by_id]
  }
  index "instance_admins_user_id_cc6e9b62" {
    columns = [column.user_id]
  }
  check "instance_admins_role_check" {
    expr = "(role >= 0)"
  }
  unique "instance_admins_instance_id_user_id_2e80a466_uniq" {
    columns = [column.instance_id, column.user_id]
  }
}
table "instance_configurations" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "key" {
    null = false
    type = character_varying(100)
  }
  column "value" {
    null = true
    type = text
  }
  column "category" {
    null = false
    type = text
  }
  column "is_encrypted" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "instance_configurations_created_by_id_e683f3e5_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "instance_configurations_updated_by_id_f0d7542e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "instance_configurations_created_by_id_e683f3e5" {
    columns = [column.created_by_id]
  }
  index "instance_configurations_key_3eb64d36_like" {
    on {
      column = column.key
      ops    = varchar_pattern_ops
    }
  }
  index "instance_configurations_updated_by_id_f0d7542e" {
    columns = [column.updated_by_id]
  }
  unique "instance_configurations_key_key" {
    columns = [column.key]
  }
}
table "instances" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "instance_name" {
    null = false
    type = character_varying(255)
  }
  column "whitelist_emails" {
    null = true
    type = text
  }
  column "instance_id" {
    null = false
    type = character_varying(255)
  }
  column "current_version" {
    null = false
    type = character_varying(255)
  }
  column "last_checked_at" {
    null = false
    type = timestamptz
  }
  column "namespace" {
    null = true
    type = character_varying(255)
  }
  column "is_telemetry_enabled" {
    null = false
    type = boolean
  }
  column "is_support_required" {
    null = false
    type = boolean
  }
  column "is_setup_done" {
    null = false
    type = boolean
  }
  column "is_signup_screen_visited" {
    null = false
    type = boolean
  }
  column "is_verified" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "domain" {
    null = false
    type = text
  }
  column "latest_version" {
    null = true
    type = character_varying(255)
  }
  column "edition" {
    null = false
    type = character_varying(255)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "is_test" {
    null = false
    type = boolean
  }
  column "is_current_version_deprecated" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "instances_created_by_id_c76e92ef_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "instances_updated_by_id_cce8fcdf_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "instances_created_by_id_c76e92ef" {
    columns = [column.created_by_id]
  }
  index "instances_instance_id_cf688621_like" {
    on {
      column = column.instance_id
      ops    = varchar_pattern_ops
    }
  }
  index "instances_updated_by_id_cce8fcdf" {
    columns = [column.updated_by_id]
  }
  unique "instances_instance_id_key" {
    columns = [column.instance_id]
  }
}
table "intake_issues" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "status" {
    null = false
    type = integer
  }
  column "snoozed_till" {
    null = true
    type = timestamptz
  }
  column "source" {
    null = true
    type = character_varying(255)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "duplicate_to_id" {
    null = true
    type = uuid
  }
  column "intake_id" {
    null = false
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "extra" {
    null = false
    type = jsonb
  }
  column "source_email" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "inbox_issues_created_by_id_483bce13_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_duplicate_to_id_6cb8d961_fk_issues_id" {
    columns     = [column.duplicate_to_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_intake_id_a04a7455_fk_intakes_id" {
    columns     = [column.intake_id]
    ref_columns = [table.intakes.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_issue_id_7d74b224_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_project_id_5117a70b_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_updated_by_id_d1b2b70f_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inbox_issues_workspace_id_4a61a7bd_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "inbox_issues_created_by_id_483bce13" {
    columns = [column.created_by_id]
  }
  index "inbox_issues_duplicate_to_id_6cb8d961" {
    columns = [column.duplicate_to_id]
  }
  index "inbox_issues_inbox_id_444b05b9" {
    columns = [column.intake_id]
  }
  index "inbox_issues_issue_id_7d74b224" {
    columns = [column.issue_id]
  }
  index "inbox_issues_project_id_5117a70b" {
    columns = [column.project_id]
  }
  index "inbox_issues_updated_by_id_d1b2b70f" {
    columns = [column.updated_by_id]
  }
  index "inbox_issues_workspace_id_4a61a7bd" {
    columns = [column.workspace_id]
  }
}
table "intakes" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "is_default" {
    null = false
    type = boolean
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "inboxes_created_by_id_9f1cf5ec_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inboxes_project_id_a0135c66_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inboxes_updated_by_id_69b7b3ae_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "inboxes_workspace_id_d6178865_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "inboxes_created_by_id_9f1cf5ec" {
    columns = [column.created_by_id]
  }
  index "inboxes_project_id_a0135c66" {
    columns = [column.project_id]
  }
  index "inboxes_updated_by_id_69b7b3ae" {
    columns = [column.updated_by_id]
  }
  index "inboxes_workspace_id_d6178865" {
    columns = [column.workspace_id]
  }
  index "intake_unique_name_project_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.project_id]
    where   = "(deleted_at IS NULL)"
  }
  unique "inboxes_name_project_id_deleted_at_95043f72_uniq" {
    columns = [column.name, column.project_id, column.deleted_at]
  }
}
table "integrations" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = false
    type = character_varying(400)
  }
  column "provider" {
    null = false
    type = character_varying(400)
  }
  column "network" {
    null = false
    type = integer
  }
  column "description" {
    null = false
    type = jsonb
  }
  column "author" {
    null = false
    type = character_varying(400)
  }
  column "webhook_url" {
    null = false
    type = text
  }
  column "webhook_secret" {
    null = false
    type = text
  }
  column "redirect_url" {
    null = false
    type = text
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "verified" {
    null = false
    type = boolean
  }
  column "avatar_url" {
    null = true
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "integrations_created_by_id_0b6edd52_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "integrations_updated_by_id_d6d00d15_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "integrations_created_by_id_0b6edd52" {
    columns = [column.created_by_id]
  }
  index "integrations_provider_6537a106_like" {
    on {
      column = column.provider
      ops    = varchar_pattern_ops
    }
  }
  index "integrations_updated_by_id_d6d00d15" {
    columns = [column.updated_by_id]
  }
  check "integrations_network_check" {
    expr = "(network >= 0)"
  }
  unique "integrations_provider_key" {
    columns = [column.provider]
  }
}
table "issue_activities" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "verb" {
    null = false
    type = character_varying(255)
  }
  column "field" {
    null = true
    type = character_varying(255)
  }
  column "old_value" {
    null = true
    type = text
  }
  column "new_value" {
    null = true
    type = text
  }
  column "comment" {
    null = false
    type = text
  }
  column "attachments" {
    null = false
    type = sql("character varying(200)[]")
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = true
    type = uuid
  }
  column "issue_comment_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "actor_id" {
    null = true
    type = uuid
  }
  column "new_identifier" {
    null = true
    type = uuid
  }
  column "old_identifier" {
    null = true
    type = uuid
  }
  column "epoch" {
    null = true
    type = double_precision
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_activities_issue_id_180e5662_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_actor_id_52fdd42d_fk_user_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_created_by_id_49516e3d_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_issue_comment_id_701f3c3c_fk_issue_comment_id" {
    columns     = [column.issue_comment_id]
    ref_columns = [table.issue_comments.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_project_id_d0ac2ccf_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_updated_by_id_0075f9bd_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_activity_workspace_id_65acaf73_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_activity_actor_id_52fdd42d" {
    columns = [column.actor_id]
  }
  index "issue_activity_created_by_id_49516e3d" {
    columns = [column.created_by_id]
  }
  index "issue_activity_issue_comment_id_701f3c3c" {
    columns = [column.issue_comment_id]
  }
  index "issue_activity_issue_id_807fbde4" {
    columns = [column.issue_id]
  }
  index "issue_activity_project_id_d0ac2ccf" {
    columns = [column.project_id]
  }
  index "issue_activity_updated_by_id_0075f9bd" {
    columns = [column.updated_by_id]
  }
  index "issue_activity_workspace_id_65acaf73" {
    columns = [column.workspace_id]
  }
}
table "issue_assignees" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "assignee_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_assignee_assignee_id_50f5c04e_fk_user_id" {
    columns     = [column.assignee_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_assignee_created_by_id_f693d43b_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_assignee_issue_id_72da08db_fk_issue_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_assignee_project_id_61c18bf2_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_assignee_updated_by_id_c54088aa_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_assignee_workspace_id_9aad55b7_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_assignee_assignee_id_50f5c04e" {
    columns = [column.assignee_id]
  }
  index "issue_assignee_created_by_id_f693d43b" {
    columns = [column.created_by_id]
  }
  index "issue_assignee_issue_id_72da08db" {
    columns = [column.issue_id]
  }
  index "issue_assignee_project_id_61c18bf2" {
    columns = [column.project_id]
  }
  index "issue_assignee_unique_issue_assignee_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.assignee_id]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_assignee_updated_by_id_c54088aa" {
    columns = [column.updated_by_id]
  }
  index "issue_assignee_workspace_id_9aad55b7" {
    columns = [column.workspace_id]
  }
  unique "issue_assignees_issue_id_assignee_id_deleted_at_b2623a0e_uniq" {
    columns = [column.issue_id, column.assignee_id, column.deleted_at]
  }
}
table "issue_attachments" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "attributes" {
    null = false
    type = jsonb
  }
  column "asset" {
    null = false
    type = character_varying(100)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_attachments_created_by_id_87be05bb_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_attachments_issue_id_0faf88bf_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_attachments_project_id_a95fe706_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_attachments_updated_by_id_47dceec1_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_attachments_workspace_id_c456a532_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_attachments_created_by_id_87be05bb" {
    columns = [column.created_by_id]
  }
  index "issue_attachments_issue_id_0faf88bf" {
    columns = [column.issue_id]
  }
  index "issue_attachments_project_id_a95fe706" {
    columns = [column.project_id]
  }
  index "issue_attachments_updated_by_id_47dceec1" {
    columns = [column.updated_by_id]
  }
  index "issue_attachments_workspace_id_c456a532" {
    columns = [column.workspace_id]
  }
}
table "issue_blockers" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "block_id" {
    null = false
    type = uuid
  }
  column "blocked_by_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_blocker_block_id_5d15a701_fk_issue_id" {
    columns     = [column.block_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_blocker_blocked_by_id_a138af71_fk_issue_id" {
    columns     = [column.blocked_by_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_blocker_created_by_id_0d19f6ea_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_blocker_project_id_380bd100_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_blocker_updated_by_id_4af87d63_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_blocker_workspace_id_419a1c71_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_blocker_block_id_5d15a701" {
    columns = [column.block_id]
  }
  index "issue_blocker_blocked_by_id_a138af71" {
    columns = [column.blocked_by_id]
  }
  index "issue_blocker_created_by_id_0d19f6ea" {
    columns = [column.created_by_id]
  }
  index "issue_blocker_project_id_380bd100" {
    columns = [column.project_id]
  }
  index "issue_blocker_updated_by_id_4af87d63" {
    columns = [column.updated_by_id]
  }
  index "issue_blocker_workspace_id_419a1c71" {
    columns = [column.workspace_id]
  }
}
table "issue_comments" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "comment_stripped" {
    null = false
    type = text
  }
  column "attachments" {
    null = false
    type = sql("character varying(200)[]")
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "actor_id" {
    null = true
    type = uuid
  }
  column "comment_html" {
    null = false
    type = text
  }
  column "comment_json" {
    null = false
    type = jsonb
  }
  column "access" {
    null = false
    type = character_varying(100)
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "edited_at" {
    null = true
    type = timestamptz
  }
  column "description_id" {
    null = true
    type = uuid
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_comment_actor_id_d312315b_fk_user_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comment_created_by_id_0765f239_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comment_issue_id_d0195e35_fk_issue_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comment_project_id_db37c105_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comment_updated_by_id_96cfb86e_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comment_workspace_id_3f7969ec_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comments_description_id_0cb72512_fk_descriptions_id" {
    columns     = [column.description_id]
    ref_columns = [table.descriptions.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_comments_parent_id_d8db10b1_fk_issue_comments_id" {
    columns     = [column.parent_id]
    ref_columns = [table.issue_comments.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_comment_actor_id_d312315b" {
    columns = [column.actor_id]
  }
  index "issue_comment_created_by_id_0765f239" {
    columns = [column.created_by_id]
  }
  index "issue_comment_issue_id_d0195e35" {
    columns = [column.issue_id]
  }
  index "issue_comment_project_id_db37c105" {
    columns = [column.project_id]
  }
  index "issue_comment_updated_by_id_96cfb86e" {
    columns = [column.updated_by_id]
  }
  index "issue_comment_workspace_id_3f7969ec" {
    columns = [column.workspace_id]
  }
  index "issue_comments_parent_id_d8db10b1" {
    columns = [column.parent_id]
  }
  unique "issue_comments_description_id_key" {
    columns = [column.description_id]
  }
}
table "issue_description_versions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "description_json" {
    null = false
    type = jsonb
  }
  column "last_saved_at" {
    null = false
    type = timestamptz
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_description_ve_workspace_id_88e930f9_fk_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_description_versions_created_by_id_3f7e62a1_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_description_versions_issue_id_c8baa13e_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_description_versions_owned_by_id_0effe4d0_fk_users_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_description_versions_project_id_536b23ef_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_description_versions_updated_by_id_6530365d_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_description_versions_created_by_id_3f7e62a1" {
    columns = [column.created_by_id]
  }
  index "issue_description_versions_issue_id_c8baa13e" {
    columns = [column.issue_id]
  }
  index "issue_description_versions_owned_by_id_0effe4d0" {
    columns = [column.owned_by_id]
  }
  index "issue_description_versions_project_id_536b23ef" {
    columns = [column.project_id]
  }
  index "issue_description_versions_updated_by_id_6530365d" {
    columns = [column.updated_by_id]
  }
  index "issue_description_versions_workspace_id_88e930f9" {
    columns = [column.workspace_id]
  }
}
table "issue_labels" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "label_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_label_created_by_id_94075315_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_label_issue_id_0f252e52_fk_issue_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_label_label_id_5f22777f_fk_label_id" {
    columns     = [column.label_id]
    ref_columns = [table.labels.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_label_project_id_eaa2ba39_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_label_updated_by_id_a97a6733_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_label_workspace_id_b5b1faac_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_label_created_by_id_94075315" {
    columns = [column.created_by_id]
  }
  index "issue_label_issue_id_0f252e52" {
    columns = [column.issue_id]
  }
  index "issue_label_label_id_5f22777f" {
    columns = [column.label_id]
  }
  index "issue_label_project_id_eaa2ba39" {
    columns = [column.project_id]
  }
  index "issue_label_updated_by_id_a97a6733" {
    columns = [column.updated_by_id]
  }
  index "issue_label_workspace_id_b5b1faac" {
    columns = [column.workspace_id]
  }
}
table "issue_links" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "url" {
    null = false
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_links_created_by_id_5e4aa092_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_links_issue_id_7032881f_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_links_project_id_63d6e9ce_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_links_updated_by_id_a771cce4_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_links_workspace_id_ff9038e7_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_links_created_by_id_5e4aa092" {
    columns = [column.created_by_id]
  }
  index "issue_links_issue_id_7032881f" {
    columns = [column.issue_id]
  }
  index "issue_links_project_id_63d6e9ce" {
    columns = [column.project_id]
  }
  index "issue_links_updated_by_id_a771cce4" {
    columns = [column.updated_by_id]
  }
  index "issue_links_workspace_id_ff9038e7" {
    columns = [column.workspace_id]
  }
}
table "issue_mentions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "mention_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_mentions_created_by_id_eb44759e_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_mentions_issue_id_d8821107_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_mentions_mention_id_cf1b9346_fk_users_id" {
    columns     = [column.mention_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_mentions_project_id_d0cccdf5_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_mentions_updated_by_id_c62106d3_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_mentions_workspace_id_4ca59d05_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_mention_unique_issue_mention_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.mention_id]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_mentions_created_by_id_eb44759e" {
    columns = [column.created_by_id]
  }
  index "issue_mentions_issue_id_d8821107" {
    columns = [column.issue_id]
  }
  index "issue_mentions_mention_id_cf1b9346" {
    columns = [column.mention_id]
  }
  index "issue_mentions_project_id_d0cccdf5" {
    columns = [column.project_id]
  }
  index "issue_mentions_updated_by_id_c62106d3" {
    columns = [column.updated_by_id]
  }
  index "issue_mentions_workspace_id_4ca59d05" {
    columns = [column.workspace_id]
  }
  unique "issue_mentions_issue_id_mention_id_deleted_at_f6ecd6ed_uniq" {
    columns = [column.issue_id, column.mention_id, column.deleted_at]
  }
}
table "issue_reactions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "reaction" {
    null = false
    type = text
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_reactions_actor_id_5f5b8303_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_reactions_created_by_id_3953b7de_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_reactions_issue_id_2c324bae_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_reactions_project_id_8708ecaf_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_reactions_updated_by_id_4069af90_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_reactions_workspace_id_bd8d7550_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_reaction_unique_issue_actor_reaction_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.actor_id, column.reaction]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_reactions_actor_id_5f5b8303" {
    columns = [column.actor_id]
  }
  index "issue_reactions_created_by_id_3953b7de" {
    columns = [column.created_by_id]
  }
  index "issue_reactions_issue_id_2c324bae" {
    columns = [column.issue_id]
  }
  index "issue_reactions_project_id_8708ecaf" {
    columns = [column.project_id]
  }
  index "issue_reactions_updated_by_id_4069af90" {
    columns = [column.updated_by_id]
  }
  index "issue_reactions_workspace_id_bd8d7550" {
    columns = [column.workspace_id]
  }
  unique "issue_reactions_issue_id_actor_id_reacti_7da73ced_uniq" {
    columns = [column.issue_id, column.actor_id, column.reaction, column.deleted_at]
  }
}
table "issue_relations" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "relation_type" {
    null = false
    type = character_varying(20)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "related_issue_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_relations_created_by_id_854d07e7_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_relations_issue_id_e1db6f72_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_relations_project_id_15350161_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_relations_related_issue_id_e1ea44a7_fk_issues_id" {
    columns     = [column.related_issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_relations_updated_by_id_3dfa850f_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_relations_workspace_id_00b50e90_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_relation_unique_issue_related_issue_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.related_issue_id]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_relations_created_by_id_854d07e7" {
    columns = [column.created_by_id]
  }
  index "issue_relations_issue_id_e1db6f72" {
    columns = [column.issue_id]
  }
  index "issue_relations_project_id_15350161" {
    columns = [column.project_id]
  }
  index "issue_relations_related_issue_id_e1ea44a7" {
    columns = [column.related_issue_id]
  }
  index "issue_relations_updated_by_id_3dfa850f" {
    columns = [column.updated_by_id]
  }
  index "issue_relations_workspace_id_00b50e90" {
    columns = [column.workspace_id]
  }
  unique "issue_relations_issue_id_related_issue_i_cc724584_uniq" {
    columns = [column.issue_id, column.related_issue_id, column.deleted_at]
  }
}
table "issue_sequences" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "sequence" {
    null = false
    type = bigint
  }
  column "deleted" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_sequence_created_by_id_59270506_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_sequence_issue_id_16e9f00f_fk_issue_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_sequence_project_id_ce882e85_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_sequence_updated_by_id_310c8dd3_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_sequence_workspace_id_0d3f0fd4_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_sequence_created_by_id_59270506" {
    columns = [column.created_by_id]
  }
  index "issue_sequence_issue_id_16e9f00f" {
    columns = [column.issue_id]
  }
  index "issue_sequence_project_id_ce882e85" {
    columns = [column.project_id]
  }
  index "issue_sequence_updated_by_id_310c8dd3" {
    columns = [column.updated_by_id]
  }
  index "issue_sequence_workspace_id_0d3f0fd4" {
    columns = [column.workspace_id]
  }
  index "issue_sequences_sequence_2c9458d4" {
    columns = [column.sequence]
  }
  check "issue_sequence_sequence_check" {
    expr = "(sequence >= 0)"
  }
}
table "issue_subscribers" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "subscriber_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_subscribers_created_by_id_b6ea0157_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_subscribers_issue_id_85cf2093_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_subscribers_project_id_cf48d75f_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_subscribers_subscriber_id_2d89c988_fk_users_id" {
    columns     = [column.subscriber_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_subscribers_updated_by_id_1bfc2f55_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_subscribers_workspace_id_96afa91f_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_subscriber_unique_issue_subscriber_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.subscriber_id]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_subscribers_created_by_id_b6ea0157" {
    columns = [column.created_by_id]
  }
  index "issue_subscribers_issue_id_85cf2093" {
    columns = [column.issue_id]
  }
  index "issue_subscribers_project_id_cf48d75f" {
    columns = [column.project_id]
  }
  index "issue_subscribers_subscriber_id_2d89c988" {
    columns = [column.subscriber_id]
  }
  index "issue_subscribers_updated_by_id_1bfc2f55" {
    columns = [column.updated_by_id]
  }
  index "issue_subscribers_workspace_id_96afa91f" {
    columns = [column.workspace_id]
  }
  unique "issue_subscribers_issue_id_subscriber_id_d_587dec1a_uniq" {
    columns = [column.issue_id, column.subscriber_id, column.deleted_at]
  }
}
table "issue_types" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "is_default" {
    null = false
    type = boolean
  }
  column "level" {
    null = false
    type = double_precision
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "is_epic" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_types_created_by_id_48764f53_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_types_updated_by_id_4919203b_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_types_workspace_id_591c6f3b_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_types_created_by_id_48764f53" {
    columns = [column.created_by_id]
  }
  index "issue_types_updated_by_id_4919203b" {
    columns = [column.updated_by_id]
  }
  index "issue_types_workspace_id_591c6f3b" {
    columns = [column.workspace_id]
  }
}
table "issue_user_properties" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "display_properties" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "display_filters" {
    null = false
    type = jsonb
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_property_created_by_id_8e92131c_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_property_project_id_30e7de7b_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_property_updated_by_id_ff158d4d_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_property_user_id_0b1d1c8f_fk_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_property_workspace_id_17860d65_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_property_created_by_id_8e92131c" {
    columns = [column.created_by_id]
  }
  index "issue_property_project_id_30e7de7b" {
    columns = [column.project_id]
  }
  index "issue_property_updated_by_id_ff158d4d" {
    columns = [column.updated_by_id]
  }
  index "issue_property_user_id_0b1d1c8f" {
    columns = [column.user_id]
  }
  index "issue_property_workspace_id_17860d65" {
    columns = [column.workspace_id]
  }
  index "issue_user_property_unique_user_project_when_deleted_at_null" {
    unique  = true
    columns = [column.user_id, column.project_id]
    where   = "(deleted_at IS NULL)"
  }
  unique "issue_user_properties_user_id_project_id_delet_2217dce5_uniq" {
    columns = [column.user_id, column.project_id, column.deleted_at]
  }
}
table "issue_versions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "parent" {
    null = true
    type = uuid
  }
  column "state" {
    null = true
    type = uuid
  }
  column "estimate_point" {
    null = true
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "priority" {
    null = false
    type = character_varying(30)
  }
  column "start_date" {
    null = true
    type = date
  }
  column "target_date" {
    null = true
    type = date
  }
  column "sequence_id" {
    null = false
    type = integer
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "completed_at" {
    null = true
    type = timestamptz
  }
  column "archived_at" {
    null = true
    type = date
  }
  column "is_draft" {
    null = false
    type = boolean
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "type" {
    null = true
    type = uuid
  }
  column "last_saved_at" {
    null = false
    type = timestamptz
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "assignees" {
    null = false
    type = sql("uuid[]")
  }
  column "labels" {
    null = false
    type = sql("uuid[]")
  }
  column "cycle" {
    null = true
    type = uuid
  }
  column "modules" {
    null = false
    type = sql("uuid[]")
  }
  column "properties" {
    null = false
    type = jsonb
  }
  column "meta" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "activity_id" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_versions_activity_id_b1872ffc_fk_issue_activities_id" {
    columns     = [column.activity_id]
    ref_columns = [table.issue_activities.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_created_by_id_a782830a_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_issue_id_25cf001c_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_owned_by_id_7586378d_fk_users_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_project_id_a069ad03_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_updated_by_id_dcae6dd2_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_versions_workspace_id_b8c48b7c_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_versions_activity_id_b1872ffc" {
    columns = [column.activity_id]
  }
  index "issue_versions_created_by_id_a782830a" {
    columns = [column.created_by_id]
  }
  index "issue_versions_issue_id_25cf001c" {
    columns = [column.issue_id]
  }
  index "issue_versions_owned_by_id_7586378d" {
    columns = [column.owned_by_id]
  }
  index "issue_versions_project_id_a069ad03" {
    columns = [column.project_id]
  }
  index "issue_versions_updated_by_id_dcae6dd2" {
    columns = [column.updated_by_id]
  }
  index "issue_versions_workspace_id_b8c48b7c" {
    columns = [column.workspace_id]
  }
}
table "issue_views" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "query" {
    null = false
    type = jsonb
  }
  column "access" {
    null = false
    type = smallint
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "display_filters" {
    null = false
    type = jsonb
  }
  column "display_properties" {
    null = false
    type = jsonb
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "is_locked" {
    null = false
    type = boolean
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_views_created_by_id_0d2e456b_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_views_owned_by_id_5e261e5d_fk_users_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_views_project_id_55ee009f_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_views_updated_by_id_28cd9870_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_views_workspace_id_8785e03d_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_views_created_by_id_0d2e456b" {
    columns = [column.created_by_id]
  }
  index "issue_views_owned_by_id_5e261e5d" {
    columns = [column.owned_by_id]
  }
  index "issue_views_project_id_55ee009f" {
    columns = [column.project_id]
  }
  index "issue_views_updated_by_id_28cd9870" {
    columns = [column.updated_by_id]
  }
  index "issue_views_workspace_id_8785e03d" {
    columns = [column.workspace_id]
  }
  check "issue_views_access_check" {
    expr = "(access >= 0)"
  }
}
table "issue_votes" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "vote" {
    null = false
    type = integer
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_votes_actor_id_525cab61_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_votes_created_by_id_86adcf5c_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_votes_issue_id_07a61ecb_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_votes_project_id_b649f55b_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_votes_updated_by_id_9e2a6cdc_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_votes_workspace_id_a3e91a6b_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_vote_unique_issue_actor_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.actor_id]
    where   = "(deleted_at IS NULL)"
  }
  index "issue_votes_actor_id_525cab61" {
    columns = [column.actor_id]
  }
  index "issue_votes_created_by_id_86adcf5c" {
    columns = [column.created_by_id]
  }
  index "issue_votes_issue_id_07a61ecb" {
    columns = [column.issue_id]
  }
  index "issue_votes_project_id_b649f55b" {
    columns = [column.project_id]
  }
  index "issue_votes_updated_by_id_9e2a6cdc" {
    columns = [column.updated_by_id]
  }
  index "issue_votes_workspace_id_a3e91a6b" {
    columns = [column.workspace_id]
  }
  unique "issue_votes_issue_id_actor_id_deleted_at_886f34e8_uniq" {
    columns = [column.issue_id, column.actor_id, column.deleted_at]
  }
}
table "issues" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = jsonb
  }
  column "priority" {
    null = false
    type = character_varying(30)
  }
  column "start_date" {
    null = true
    type = date
  }
  column "target_date" {
    null = true
    type = date
  }
  column "sequence_id" {
    null = false
    type = integer
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "state_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "completed_at" {
    null = true
    type = timestamptz
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "point" {
    null = true
    type = integer
  }
  column "archived_at" {
    null = true
    type = date
  }
  column "is_draft" {
    null = false
    type = boolean
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "estimate_point_id" {
    null = true
    type = uuid
  }
  column "type_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_created_by_id_8f0ae62b_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_parent_id_ce8d76ba_fk_issue_id" {
    columns     = [column.parent_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_project_id_fea0fc80_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_state_id_1a65560d_fk_state_id" {
    columns     = [column.state_id]
    ref_columns = [table.states.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_updated_by_id_f1261863_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_workspace_id_c84878c1_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issues_estimate_point_id_a6822abe_fk_estimate_points_id" {
    columns     = [column.estimate_point_id]
    ref_columns = [table.estimate_points.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issues_type_id_a4710b19_fk_issue_types_id" {
    columns     = [column.type_id]
    ref_columns = [table.issue_types.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_created_by_id_8f0ae62b" {
    columns = [column.created_by_id]
  }
  index "issue_parent_id_ce8d76ba" {
    columns = [column.parent_id]
  }
  index "issue_project_id_fea0fc80" {
    columns = [column.project_id]
  }
  index "issue_state_id_1a65560d" {
    columns = [column.state_id]
  }
  index "issue_updated_by_id_f1261863" {
    columns = [column.updated_by_id]
  }
  index "issue_workspace_id_c84878c1" {
    columns = [column.workspace_id]
  }
  index "issues_estimate_point_id_a6822abe" {
    columns = [column.estimate_point_id]
  }
  index "issues_type_id_a4710b19" {
    columns = [column.type_id]
  }
}
table "labels" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  column "color" {
    null = false
    type = character_varying(255)
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "label_created_by_id_aa6ffcfa_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "label_parent_id_7a853296_fk_label_id" {
    columns     = [column.parent_id]
    ref_columns = [table.labels.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "label_updated_by_id_894a5464_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "label_workspace_id_c4c9ae5a_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "labels_project_id_cf57a802_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "label_created_by_id_aa6ffcfa" {
    columns = [column.created_by_id]
  }
  index "label_parent_id_7a853296" {
    columns = [column.parent_id]
  }
  index "label_project_id_90e0f1a2" {
    columns = [column.project_id]
  }
  index "label_updated_by_id_894a5464" {
    columns = [column.updated_by_id]
  }
  index "label_workspace_id_c4c9ae5a" {
    columns = [column.workspace_id]
  }
  index "unique_name_when_project_null_and_not_deleted" {
    unique  = true
    columns = [column.name]
    where   = "((deleted_at IS NULL) AND (project_id IS NULL))"
  }
  index "unique_project_name_when_not_deleted" {
    unique  = true
    columns = [column.project_id, column.name]
    where   = "((deleted_at IS NULL) AND (project_id IS NOT NULL))"
  }
}
table "module_issues" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_id" {
    null = false
    type = uuid
  }
  column "module_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "module_issues_created_by_id_de0b995a_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_issues_issue_id_7caa908b_fk_issues_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issues.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_issues_module_id_74e0ed5a_fk_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.modules.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_issues_project_id_59836d1e_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_issues_updated_by_id_46dbf724_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_issues_workspace_id_6bf85201_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "module_issue_unique_issue_module_when_deleted_at_null" {
    unique  = true
    columns = [column.issue_id, column.module_id]
    where   = "(deleted_at IS NULL)"
  }
  index "module_issues_created_by_id_de0b995a" {
    columns = [column.created_by_id]
  }
  index "module_issues_issue_id_7caa908b" {
    columns = [column.issue_id]
  }
  index "module_issues_module_id_74e0ed5a" {
    columns = [column.module_id]
  }
  index "module_issues_project_id_59836d1e" {
    columns = [column.project_id]
  }
  index "module_issues_updated_by_id_46dbf724" {
    columns = [column.updated_by_id]
  }
  index "module_issues_workspace_id_6bf85201" {
    columns = [column.workspace_id]
  }
  unique "module_issues_issue_id_module_id_deleted_at_f944f7c9_uniq" {
    columns = [column.issue_id, column.module_id, column.deleted_at]
  }
}
table "module_links" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "url" {
    null = false
    type = character_varying(200)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "module_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "module_links_created_by_id_eaf6492f_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_links_module_id_0fda3f8a_fk_modules_id" {
    columns     = [column.module_id]
    ref_columns = [table.modules.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_links_project_id_f720bb79_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_links_updated_by_id_4da419e7_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_links_workspace_id_0521c11c_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "module_links_created_by_id_eaf6492f" {
    columns = [column.created_by_id]
  }
  index "module_links_module_id_0fda3f8a" {
    columns = [column.module_id]
  }
  index "module_links_project_id_f720bb79" {
    columns = [column.project_id]
  }
  index "module_links_updated_by_id_4da419e7" {
    columns = [column.updated_by_id]
  }
  index "module_links_workspace_id_0521c11c" {
    columns = [column.workspace_id]
  }
}
table "module_members" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "member_id" {
    null = false
    type = uuid
  }
  column "module_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "module_member_created_by_id_2ed84a65_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_member_member_id_928f473e_fk_user_id" {
    columns     = [column.member_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_member_module_id_f00be7ef_fk_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.modules.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_member_project_id_ec8d2376_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_member_updated_by_id_a9046438_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_member_workspace_id_f2f23c73_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "module_member_created_by_id_2ed84a65" {
    columns = [column.created_by_id]
  }
  index "module_member_member_id_928f473e" {
    columns = [column.member_id]
  }
  index "module_member_module_id_f00be7ef" {
    columns = [column.module_id]
  }
  index "module_member_project_id_ec8d2376" {
    columns = [column.project_id]
  }
  index "module_member_unique_module_member_when_deleted_at_null" {
    unique  = true
    columns = [column.module_id, column.member_id]
    where   = "(deleted_at IS NULL)"
  }
  index "module_member_updated_by_id_a9046438" {
    columns = [column.updated_by_id]
  }
  index "module_member_workspace_id_f2f23c73" {
    columns = [column.workspace_id]
  }
  unique "module_members_module_id_member_id_deleted_at_bb7a6f00_uniq" {
    columns = [column.module_id, column.member_id, column.deleted_at]
  }
}
table "module_user_properties" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "display_filters" {
    null = false
    type = jsonb
  }
  column "display_properties" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "module_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "module_user_properties_created_by_id_bdd98440_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_user_properties_module_id_e95b158a_fk_modules_id" {
    columns     = [column.module_id]
    ref_columns = [table.modules.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_user_properties_project_id_3c5a4972_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_user_properties_updated_by_id_b7dafc77_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_user_properties_user_id_e83a1c2c_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_user_properties_workspace_id_ddaf807c_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "module_user_properties_created_by_id_bdd98440" {
    columns = [column.created_by_id]
  }
  index "module_user_properties_module_id_e95b158a" {
    columns = [column.module_id]
  }
  index "module_user_properties_project_id_3c5a4972" {
    columns = [column.project_id]
  }
  index "module_user_properties_unique_module_user_when_deleted_at_null" {
    unique  = true
    columns = [column.module_id, column.user_id]
    where   = "(deleted_at IS NULL)"
  }
  index "module_user_properties_updated_by_id_b7dafc77" {
    columns = [column.updated_by_id]
  }
  index "module_user_properties_user_id_e83a1c2c" {
    columns = [column.user_id]
  }
  index "module_user_properties_workspace_id_ddaf807c" {
    columns = [column.workspace_id]
  }
  unique "module_user_properties_module_id_user_id_delete_3269582d_uniq" {
    columns = [column.module_id, column.user_id, column.deleted_at]
  }
}
table "modules" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "description_text" {
    null = true
    type = jsonb
  }
  column "description_html" {
    null = true
    type = jsonb
  }
  column "start_date" {
    null = true
    type = date
  }
  column "target_date" {
    null = true
    type = date
  }
  column "status" {
    null = false
    type = character_varying(20)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "lead_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "archived_at" {
    null = true
    type = timestamptz
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "module_created_by_id_ff7a5866_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_lead_id_04966630_fk_user_id" {
    columns     = [column.lead_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_project_id_da84b04f_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_updated_by_id_72ab6d5c_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "module_workspace_id_0a826fef_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "module_created_by_id_ff7a5866" {
    columns = [column.created_by_id]
  }
  index "module_lead_id_04966630" {
    columns = [column.lead_id]
  }
  index "module_project_id_da84b04f" {
    columns = [column.project_id]
  }
  index "module_unique_name_project_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.project_id]
    where   = "(deleted_at IS NULL)"
  }
  index "module_updated_by_id_72ab6d5c" {
    columns = [column.updated_by_id]
  }
  index "module_workspace_id_0a826fef" {
    columns = [column.workspace_id]
  }
  unique "modules_name_project_id_deleted_at_328e2346_uniq" {
    columns = [column.name, column.project_id, column.deleted_at]
  }
}
table "notifications" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "entity_name" {
    null = false
    type = character_varying(255)
  }
  column "title" {
    null = false
    type = text
  }
  column "message" {
    null = true
    type = jsonb
  }
  column "message_html" {
    null = false
    type = text
  }
  column "message_stripped" {
    null = true
    type = text
  }
  column "sender" {
    null = false
    type = character_varying(255)
  }
  column "read_at" {
    null = true
    type = timestamptz
  }
  column "snoozed_till" {
    null = true
    type = timestamptz
  }
  column "archived_at" {
    null = true
    type = timestamptz
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "receiver_id" {
    null = false
    type = uuid
  }
  column "triggered_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "notifications_created_by_id_b9c3f81b_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "notifications_project_id_e4d4f192_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "notifications_receiver_id_b708b2b0_fk_users_id" {
    columns     = [column.receiver_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "notifications_triggered_by_id_31cdec21_fk_users_id" {
    columns     = [column.triggered_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "notifications_updated_by_id_8a651e96_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "notifications_workspace_id_b2f09ef7_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "notif_entity_identifier_idx" {
    columns = [column.entity_identifier]
  }
  index "notif_entity_idx" {
    columns = [column.receiver_id, column.read_at]
  }
  index "notif_entity_lookup_idx" {
    columns = [column.workspace_id, column.entity_identifier, column.entity_name]
  }
  index "notif_entity_name_idx" {
    columns = [column.entity_name]
  }
  index "notif_read_at_idx" {
    columns = [column.read_at]
  }
  index "notif_receiver_entity_idx" {
    columns = [column.receiver_id, column.workspace_id, column.entity_name, column.read_at]
  }
  index "notif_receiver_sender_idx" {
    columns = [column.receiver_id, column.workspace_id, column.sender]
  }
  index "notif_receiver_state_idx" {
    columns = [column.receiver_id, column.workspace_id, column.snoozed_till, column.archived_at]
  }
  index "notif_receiver_status_idx" {
    columns = [column.receiver_id, column.workspace_id, column.read_at, column.created_at]
  }
  index "notifications_created_by_id_b9c3f81b" {
    columns = [column.created_by_id]
  }
  index "notifications_project_id_e4d4f192" {
    columns = [column.project_id]
  }
  index "notifications_receiver_id_b708b2b0" {
    columns = [column.receiver_id]
  }
  index "notifications_triggered_by_id_31cdec21" {
    columns = [column.triggered_by_id]
  }
  index "notifications_updated_by_id_8a651e96" {
    columns = [column.updated_by_id]
  }
  index "notifications_workspace_id_b2f09ef7" {
    columns = [column.workspace_id]
  }
}
table "page_labels" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "label_id" {
    null = false
    type = uuid
  }
  column "page_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "page_labels_created_by_id_fbd942c0_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_labels_label_id_05958e53_fk_labels_id" {
    columns     = [column.label_id]
    ref_columns = [table.labels.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_labels_page_id_0e6cdb3d_fk_pages_id" {
    columns     = [column.page_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_labels_updated_by_id_d9fddbff_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_labels_workspace_id_078bb01c_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "page_labels_created_by_id_fbd942c0" {
    columns = [column.created_by_id]
  }
  index "page_labels_label_id_05958e53" {
    columns = [column.label_id]
  }
  index "page_labels_page_id_0e6cdb3d" {
    columns = [column.page_id]
  }
  index "page_labels_updated_by_id_d9fddbff" {
    columns = [column.updated_by_id]
  }
  index "page_labels_workspace_id_078bb01c" {
    columns = [column.workspace_id]
  }
}
table "page_logs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "transaction" {
    null = false
    type = uuid
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "entity_name" {
    null = false
    type = character_varying(30)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "page_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "entity_type" {
    null = true
    type = character_varying(30)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "page_logs_created_by_id_4a295aec_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_logs_page_id_0e0d747d_fk_pages_id" {
    columns     = [column.page_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_logs_updated_by_id_1995190b_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_logs_workspace_id_be7bde64_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "page_logs_created_by_id_4a295aec" {
    columns = [column.created_by_id]
  }
  index "page_logs_page_id_0e0d747d" {
    columns = [column.page_id]
  }
  index "page_logs_updated_by_id_1995190b" {
    columns = [column.updated_by_id]
  }
  index "page_logs_workspace_id_be7bde64" {
    columns = [column.workspace_id]
  }
  index "pagelog_entity_id_idx" {
    columns = [column.entity_identifier]
  }
  index "pagelog_entity_name_idx" {
    columns = [column.entity_name]
  }
  index "pagelog_entity_type_idx" {
    columns = [column.entity_type]
  }
  index "pagelog_name_id_idx" {
    columns = [column.entity_name, column.entity_identifier]
  }
  index "pagelog_type_id_idx" {
    columns = [column.entity_type, column.entity_identifier]
  }
  unique "page_logs_page_id_transaction_9ab05334_uniq" {
    columns = [column.page_id, column.transaction]
  }
}
table "page_versions" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "last_saved_at" {
    null = false
    type = timestamptz
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "description_json" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "page_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "sub_pages_data" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "page_versions_created_by_id_d660b13b_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_versions_owned_by_id_6d9143db_fk_users_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_versions_page_id_c46471da_fk_pages_id" {
    columns     = [column.page_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_versions_updated_by_id_72d5e579_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "page_versions_workspace_id_8330a200_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "page_versions_created_by_id_d660b13b" {
    columns = [column.created_by_id]
  }
  index "page_versions_owned_by_id_6d9143db" {
    columns = [column.owned_by_id]
  }
  index "page_versions_page_id_c46471da" {
    columns = [column.page_id]
  }
  index "page_versions_updated_by_id_72d5e579" {
    columns = [column.updated_by_id]
  }
  index "page_versions_workspace_id_8330a200" {
    columns = [column.workspace_id]
  }
}
table "pages" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = jsonb
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "access" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owned_by_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "color" {
    null = false
    type = character_varying(255)
  }
  column "archived_at" {
    null = true
    type = date
  }
  column "is_locked" {
    null = false
    type = boolean
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "is_global" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "moved_to_page" {
    null = true
    type = uuid
  }
  column "moved_to_project" {
    null = true
    type = uuid
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "pages_created_by_id_d109a675_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "pages_owned_by_id_bf50485f_fk_users_id" {
    columns     = [column.owned_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "pages_parent_id_8b823409_fk_pages_id" {
    columns     = [column.parent_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "pages_updated_by_id_6c42de3e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "pages_workspace_id_c6c51010_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "pages_created_by_id_d109a675" {
    columns = [column.created_by_id]
  }
  index "pages_owned_by_id_bf50485f" {
    columns = [column.owned_by_id]
  }
  index "pages_parent_id_8b823409" {
    columns = [column.parent_id]
  }
  index "pages_updated_by_id_6c42de3e" {
    columns = [column.updated_by_id]
  }
  index "pages_workspace_id_c6c51010" {
    columns = [column.workspace_id]
  }
  check "pages_access_check" {
    expr = "(access >= 0)"
  }
}
table "profiles" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "theme" {
    null = false
    type = jsonb
  }
  column "is_tour_completed" {
    null = false
    type = boolean
  }
  column "onboarding_step" {
    null = false
    type = jsonb
  }
  column "use_case" {
    null = true
    type = text
  }
  column "role" {
    null = true
    type = character_varying(300)
  }
  column "is_onboarded" {
    null = false
    type = boolean
  }
  column "last_workspace_id" {
    null = true
    type = uuid
  }
  column "billing_address_country" {
    null = false
    type = character_varying(255)
  }
  column "billing_address" {
    null = true
    type = jsonb
  }
  column "has_billing_address" {
    null = false
    type = boolean
  }
  column "company_name" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "is_mobile_onboarded" {
    null = false
    type = boolean
  }
  column "mobile_onboarding_step" {
    null = false
    type = jsonb
  }
  column "mobile_timezone_auto_set" {
    null = false
    type = boolean
  }
  column "language" {
    null = false
    type = character_varying(255)
  }
  column "is_smooth_cursor_enabled" {
    null = false
    type = boolean
  }
  column "start_of_the_week" {
    null = false
    type = smallint
  }
  column "is_app_rail_docked" {
    null = false
    type = boolean
  }
  column "background_color" {
    null = false
    type = character_varying(255)
  }
  column "goals" {
    null = false
    type = jsonb
  }
  column "has_marketing_email_consent" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "profiles_user_id_36580373_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "profiles_start_of_the_week_check" {
    expr = "(start_of_the_week >= 0)"
  }
  unique "profiles_user_id_key" {
    columns = [column.user_id]
  }
}
table "project_deploy_boards" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "anchor" {
    null = false
    type = character_varying(255)
  }
  column "comments" {
    null = false
    type = boolean
  }
  column "reactions" {
    null = false
    type = boolean
  }
  column "votes" {
    null = false
    type = boolean
  }
  column "views" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "intake_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_deploy_boards_created_by_id_2ea72f98_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_deploy_boards_intake_id_36aa612d_fk_intakes_id" {
    columns     = [column.intake_id]
    ref_columns = [table.intakes.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_deploy_boards_project_id_49d887b2_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_deploy_boards_updated_by_id_290eb99e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_deploy_boards_workspace_id_cd92f164_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_deploy_boards_anchor_b61b8817_like" {
    on {
      column = column.anchor
      ops    = varchar_pattern_ops
    }
  }
  index "project_deploy_boards_created_by_id_2ea72f98" {
    columns = [column.created_by_id]
  }
  index "project_deploy_boards_inbox_id_a6a75525" {
    columns = [column.intake_id]
  }
  index "project_deploy_boards_project_id_49d887b2" {
    columns = [column.project_id]
  }
  index "project_deploy_boards_updated_by_id_290eb99e" {
    columns = [column.updated_by_id]
  }
  index "project_deploy_boards_workspace_id_cd92f164" {
    columns = [column.workspace_id]
  }
  unique "project_deploy_boards_anchor_key" {
    columns = [column.anchor]
  }
  unique "project_deploy_boards_project_id_anchor_893d365a_uniq" {
    columns = [column.project_id, column.anchor]
  }
}
table "project_identifiers" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(12)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_identifier_created_by_id_2b6f273a_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_identifier_project_id_13de58a9_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_identifier_updated_by_id_1a00e2a0_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_identifier_workspace_id_6024b517_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_identifier_created_by_id_2b6f273a" {
    columns = [column.created_by_id]
  }
  index "project_identifier_updated_by_id_1a00e2a0" {
    columns = [column.updated_by_id]
  }
  index "project_identifier_workspace_id_6024b517" {
    columns = [column.workspace_id]
  }
  index "project_identifiers_name_6ca8a4b0" {
    columns = [column.name]
  }
  index "project_identifiers_name_6ca8a4b0_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "unique_name_workspace_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.workspace_id]
    where   = "(deleted_at IS NULL)"
  }
  unique "project_identifier_project_id_key" {
    columns = [column.project_id]
  }
  unique "project_identifiers_name_workspace_id_deleted_at_d332e701_uniq" {
    columns = [column.name, column.workspace_id, column.deleted_at]
  }
}
table "project_issue_types" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "level" {
    null = false
    type = integer
  }
  column "is_default" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "issue_type_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_issue_types_created_by_id_049cecfd_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_issue_types_issue_type_id_9494de9f_fk_issue_types_id" {
    columns     = [column.issue_type_id]
    ref_columns = [table.issue_types.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_issue_types_project_id_ef6e52e4_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_issue_types_updated_by_id_b5998397_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_issue_types_workspace_id_ace3c5b5_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_issue_type_unique_project_issue_type_when_deleted_at_nu" {
    unique  = true
    columns = [column.project_id, column.issue_type_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_issue_types_created_by_id_049cecfd" {
    columns = [column.created_by_id]
  }
  index "project_issue_types_issue_type_id_9494de9f" {
    columns = [column.issue_type_id]
  }
  index "project_issue_types_project_id_ef6e52e4" {
    columns = [column.project_id]
  }
  index "project_issue_types_updated_by_id_b5998397" {
    columns = [column.updated_by_id]
  }
  index "project_issue_types_workspace_id_ace3c5b5" {
    columns = [column.workspace_id]
  }
  check "project_issue_types_level_check" {
    expr = "(level >= 0)"
  }
  unique "project_issue_types_project_id_issue_type_id_2287e5dc_uniq" {
    columns = [column.project_id, column.issue_type_id, column.deleted_at]
  }
}
table "project_member_invites" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "accepted" {
    null = false
    type = boolean
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "message" {
    null = true
    type = text
  }
  column "responded_at" {
    null = true
    type = timestamptz
  }
  column "role" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_member_invite_created_by_id_a87df45c_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_invite_project_id_8fb7750e_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_invite_updated_by_id_5aa55c96_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_invite_workspace_id_64e2dc4c_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_member_invite_created_by_id_a87df45c" {
    columns = [column.created_by_id]
  }
  index "project_member_invite_project_id_8fb7750e" {
    columns = [column.project_id]
  }
  index "project_member_invite_updated_by_id_5aa55c96" {
    columns = [column.updated_by_id]
  }
  index "project_member_invite_workspace_id_64e2dc4c" {
    columns = [column.workspace_id]
  }
  check "project_member_invite_role_check" {
    expr = "(role >= 0)"
  }
}
table "project_members" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "comment" {
    null = true
    type = text
  }
  column "role" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "member_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "default_props" {
    null = false
    type = jsonb
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "preferences" {
    null = false
    type = jsonb
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_member_created_by_id_8b363306_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_member_id_9d6b126b_fk_user_id" {
    columns     = [column.member_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_project_id_11ea1a9e_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_updated_by_id_cf6aaac4_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_member_workspace_id_88bb9a97_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_member_created_by_id_8b363306" {
    columns = [column.created_by_id]
  }
  index "project_member_member_id_9d6b126b" {
    columns = [column.member_id]
  }
  index "project_member_project_id_11ea1a9e" {
    columns = [column.project_id]
  }
  index "project_member_unique_project_member_when_deleted_at_null" {
    unique  = true
    columns = [column.project_id, column.member_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_member_updated_by_id_cf6aaac4" {
    columns = [column.updated_by_id]
  }
  index "project_member_workspace_id_88bb9a97" {
    columns = [column.workspace_id]
  }
  check "project_member_role_check" {
    expr = "(role >= 0)"
  }
  unique "project_members_project_id_member_id_deleted_at_0299122d_uniq" {
    columns = [column.project_id, column.member_id, column.deleted_at]
  }
}
table "project_pages" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "page_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_pages_created_by_id_b9d02062_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_pages_page_id_a0f54439_fk_pages_id" {
    columns     = [column.page_id]
    ref_columns = [table.pages.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_pages_project_id_376ba35a_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_pages_updated_by_id_b80bf0f4_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_pages_workspace_id_13ed9e73_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_page_unique_project_page_when_deleted_at_null" {
    unique  = true
    columns = [column.project_id, column.page_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_pages_created_by_id_b9d02062" {
    columns = [column.created_by_id]
  }
  index "project_pages_page_id_a0f54439" {
    columns = [column.page_id]
  }
  index "project_pages_project_id_376ba35a" {
    columns = [column.project_id]
  }
  index "project_pages_updated_by_id_b80bf0f4" {
    columns = [column.updated_by_id]
  }
  index "project_pages_workspace_id_13ed9e73" {
    columns = [column.workspace_id]
  }
  unique "project_pages_project_id_page_id_deleted_at_7c80a40c_uniq" {
    columns = [column.project_id, column.page_id, column.deleted_at]
  }
}
table "project_public_members" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "member_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_public_members_created_by_id_c4c7c776_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_public_members_member_id_52f257f9_fk_users_id" {
    columns     = [column.member_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_public_members_project_id_2dfd893d_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_public_members_updated_by_id_c3e4d675_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_public_members_workspace_id_ebfce110_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_public_member_unique_project_member_when_deleted_at_nul" {
    unique  = true
    columns = [column.project_id, column.member_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_public_members_created_by_id_c4c7c776" {
    columns = [column.created_by_id]
  }
  index "project_public_members_member_id_52f257f9" {
    columns = [column.member_id]
  }
  index "project_public_members_project_id_2dfd893d" {
    columns = [column.project_id]
  }
  index "project_public_members_updated_by_id_c3e4d675" {
    columns = [column.updated_by_id]
  }
  index "project_public_members_workspace_id_ebfce110" {
    columns = [column.workspace_id]
  }
  unique "project_public_members_project_id_member_id_del_9acd89b5_uniq" {
    columns = [column.project_id, column.member_id, column.deleted_at]
  }
}
table "project_webhooks" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "webhook_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_webhooks_created_by_id_c3e4bfa3_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_webhooks_project_id_bec3cf8c_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_webhooks_updated_by_id_a0183aeb_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_webhooks_webhook_id_da27c6a7_fk_webhooks_id" {
    columns     = [column.webhook_id]
    ref_columns = [table.webhooks.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_webhooks_workspace_id_429ebf05_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_webhook_unique_project_webhook_when_deleted_at_null" {
    unique  = true
    columns = [column.project_id, column.webhook_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_webhooks_created_by_id_c3e4bfa3" {
    columns = [column.created_by_id]
  }
  index "project_webhooks_project_id_bec3cf8c" {
    columns = [column.project_id]
  }
  index "project_webhooks_updated_by_id_a0183aeb" {
    columns = [column.updated_by_id]
  }
  index "project_webhooks_webhook_id_da27c6a7" {
    columns = [column.webhook_id]
  }
  index "project_webhooks_workspace_id_429ebf05" {
    columns = [column.workspace_id]
  }
  unique "project_webhooks_project_id_webhook_id_deleted_at_dcfdb35d_uniq" {
    columns = [column.project_id, column.webhook_id, column.deleted_at]
  }
}
table "projects" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "description_text" {
    null = true
    type = jsonb
  }
  column "description_html" {
    null = true
    type = jsonb
  }
  column "network" {
    null = false
    type = smallint
  }
  column "identifier" {
    null = false
    type = character_varying(12)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "default_assignee_id" {
    null = true
    type = uuid
  }
  column "project_lead_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "emoji" {
    null = true
    type = character_varying(255)
  }
  column "cycle_view" {
    null = false
    type = boolean
  }
  column "module_view" {
    null = false
    type = boolean
  }
  column "cover_image" {
    null = true
    type = text
  }
  column "issue_views_view" {
    null = false
    type = boolean
  }
  column "page_view" {
    null = false
    type = boolean
  }
  column "estimate_id" {
    null = true
    type = uuid
  }
  column "icon_prop" {
    null = true
    type = jsonb
  }
  column "intake_view" {
    null = false
    type = boolean
  }
  column "archive_in" {
    null = false
    type = integer
  }
  column "close_in" {
    null = false
    type = integer
  }
  column "default_state_id" {
    null = true
    type = uuid
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "archived_at" {
    null = true
    type = timestamptz
  }
  column "is_time_tracking_enabled" {
    null = false
    type = boolean
  }
  column "is_issue_type_enabled" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "guest_view_all_features" {
    null = false
    type = boolean
  }
  column "timezone" {
    null = false
    type = character_varying(255)
  }
  column "cover_image_asset_id" {
    null = true
    type = uuid
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "project_created_by_id_6cc13408_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_default_assignee_id_6ba45f90_fk_user_id" {
    columns     = [column.default_assignee_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_project_lead_id_caf8e353_fk_user_id" {
    columns     = [column.project_lead_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_updated_by_id_fe290525_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "project_workspace_id_01764ff9_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "projects_cover_image_asset_id_e6636b92_fk_file_assets_id" {
    columns     = [column.cover_image_asset_id]
    ref_columns = [table.file_assets.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "projects_default_state_id_f13e8b95_fk_states_id" {
    columns     = [column.default_state_id]
    ref_columns = [table.states.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "projects_estimate_id_85c7b2ac_fk_estimates_id" {
    columns     = [column.estimate_id]
    ref_columns = [table.estimates.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "project_created_by_id_6cc13408" {
    columns = [column.created_by_id]
  }
  index "project_default_assignee_id_6ba45f90" {
    columns = [column.default_assignee_id]
  }
  index "project_project_lead_id_caf8e353" {
    columns = [column.project_lead_id]
  }
  index "project_unique_identifier_workspace_when_deleted_at_null" {
    unique  = true
    columns = [column.identifier, column.workspace_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_unique_name_workspace_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.workspace_id]
    where   = "(deleted_at IS NULL)"
  }
  index "project_updated_by_id_fe290525" {
    columns = [column.updated_by_id]
  }
  index "project_workspace_id_01764ff9" {
    columns = [column.workspace_id]
  }
  index "projects_cover_image_asset_id_e6636b92" {
    columns = [column.cover_image_asset_id]
  }
  index "projects_default_state_id_f13e8b95" {
    columns = [column.default_state_id]
  }
  index "projects_estimate_id_85c7b2ac" {
    columns = [column.estimate_id]
  }
  index "projects_identifier_3267ade8" {
    columns = [column.identifier]
  }
  index "projects_identifier_3267ade8_like" {
    on {
      column = column.identifier
      ops    = varchar_pattern_ops
    }
  }
  check "project_network_check" {
    expr = "(network >= 0)"
  }
  unique "projects_identifier_workspace_id_deleted_at_7d2fa8c1_uniq" {
    columns = [column.identifier, column.workspace_id, column.deleted_at]
  }
  unique "projects_name_workspace_id_deleted_at_c7aa56f7_uniq" {
    columns = [column.name, column.workspace_id, column.deleted_at]
  }
}
table "sessions" {
  schema = schema.public
  column "session_data" {
    null = false
    type = text
  }
  column "expire_date" {
    null = false
    type = timestamptz
  }
  column "device_info" {
    null = true
    type = jsonb
  }
  column "session_key" {
    null = false
    type = character_varying(128)
  }
  column "user_id" {
    null = true
    type = character_varying(50)
  }
  primary_key {
    columns = [column.session_key]
  }
  index "sessions_expire_date_16e4c444" {
    columns = [column.expire_date]
  }
  index "sessions_session_key_58f9471b_like" {
    on {
      column = column.session_key
      ops    = varchar_pattern_ops
    }
  }
  index "sessions_user_id_05e26f4a" {
    columns = [column.user_id]
  }
  index "sessions_user_id_05e26f4a_like" {
    on {
      column = column.user_id
      ops    = varchar_pattern_ops
    }
  }
}
table "slack_project_syncs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "access_token" {
    null = false
    type = character_varying(300)
  }
  column "scopes" {
    null = false
    type = text
  }
  column "bot_user_id" {
    null = false
    type = character_varying(50)
  }
  column "webhook_url" {
    null = false
    type = character_varying(1000)
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "team_id" {
    null = false
    type = character_varying(30)
  }
  column "team_name" {
    null = false
    type = character_varying(300)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "workspace_integration_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "slack_project_syncs_created_by_id_ec405a17_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "slack_project_syncs_project_id_016dc792_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "slack_project_syncs_updated_by_id_152eb3b5_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "slack_project_syncs_workspace_id_d1822b06_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "slack_project_syncs_workspace_integratio_d89c9b40_fk_workspace" {
    columns     = [column.workspace_integration_id]
    ref_columns = [table.workspace_integrations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "slack_project_syncs_created_by_id_ec405a17" {
    columns = [column.created_by_id]
  }
  index "slack_project_syncs_project_id_016dc792" {
    columns = [column.project_id]
  }
  index "slack_project_syncs_updated_by_id_152eb3b5" {
    columns = [column.updated_by_id]
  }
  index "slack_project_syncs_workspace_id_d1822b06" {
    columns = [column.workspace_id]
  }
  index "slack_project_syncs_workspace_integration_id_d89c9b40" {
    columns = [column.workspace_integration_id]
  }
  unique "slack_project_syncs_team_id_project_id_50a144a7_uniq" {
    columns = [column.team_id, column.project_id]
  }
}
table "social_login_connections" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "medium" {
    null = false
    type = character_varying(20)
  }
  column "last_login_at" {
    null = true
    type = timestamptz
  }
  column "last_received_at" {
    null = true
    type = timestamptz
  }
  column "token_data" {
    null = true
    type = jsonb
  }
  column "extra_data" {
    null = true
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "social_login_connection_created_by_id_7ca2ef50_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "social_login_connection_updated_by_id_c13deb42_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "social_login_connection_user_id_0e26c0c5_fk_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "social_login_connection_created_by_id_7ca2ef50" {
    columns = [column.created_by_id]
  }
  index "social_login_connection_updated_by_id_c13deb42" {
    columns = [column.updated_by_id]
  }
  index "social_login_connection_user_id_0e26c0c5" {
    columns = [column.user_id]
  }
}
table "states" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "color" {
    null = false
    type = character_varying(255)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "sequence" {
    null = false
    type = double_precision
  }
  column "group" {
    null = false
    type = character_varying(20)
  }
  column "default" {
    null = false
    type = boolean
  }
  column "external_id" {
    null = true
    type = character_varying(255)
  }
  column "external_source" {
    null = true
    type = character_varying(255)
  }
  column "is_triage" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "state_created_by_id_ff51a50d_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "state_project_id_23a65fd6_fk_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "state_updated_by_id_be298453_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "state_workspace_id_2293282d_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "state_created_by_id_ff51a50d" {
    columns = [column.created_by_id]
  }
  index "state_project_id_23a65fd6" {
    columns = [column.project_id]
  }
  index "state_slug_bab0af35" {
    columns = [column.slug]
  }
  index "state_slug_bab0af35_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "state_unique_name_project_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.project_id]
    where   = "(deleted_at IS NULL)"
  }
  index "state_updated_by_id_be298453" {
    columns = [column.updated_by_id]
  }
  index "state_workspace_id_2293282d" {
    columns = [column.workspace_id]
  }
  unique "states_name_project_id_deleted_at_02f90488_uniq" {
    columns = [column.name, column.project_id, column.deleted_at]
  }
}
table "stickies" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = true
    type = text
  }
  column "description" {
    null = false
    type = jsonb
  }
  column "description_html" {
    null = false
    type = text
  }
  column "description_stripped" {
    null = true
    type = text
  }
  column "description_binary" {
    null = true
    type = bytea
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "color" {
    null = true
    type = character_varying(255)
  }
  column "background_color" {
    null = true
    type = character_varying(255)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owner_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "stickies_created_by_id_f72e05c4_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "stickies_owner_id_6ee3be2b_fk_users_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "stickies_updated_by_id_d660f1fb_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "stickies_workspace_id_0094496a_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "stickies_created_by_id_f72e05c4" {
    columns = [column.created_by_id]
  }
  index "stickies_owner_id_6ee3be2b" {
    columns = [column.owner_id]
  }
  index "stickies_updated_by_id_d660f1fb" {
    columns = [column.updated_by_id]
  }
  index "stickies_workspace_id_0094496a" {
    columns = [column.workspace_id]
  }
}
table "teams" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = text
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "logo_props" {
    null = false
    type = jsonb
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "team_created_by_id_725a9101_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "team_updated_by_id_79bb36f2_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "team_workspace_id_1d56407f_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "team_created_by_id_725a9101" {
    columns = [column.created_by_id]
  }
  index "team_unique_name_workspace_when_deleted_at_null" {
    unique  = true
    columns = [column.name, column.workspace_id]
    where   = "(deleted_at IS NULL)"
  }
  index "team_updated_by_id_79bb36f2" {
    columns = [column.updated_by_id]
  }
  index "team_workspace_id_1d56407f" {
    columns = [column.workspace_id]
  }
  unique "teams_name_workspace_id_deleted_at_4b131aa2_uniq" {
    columns = [column.name, column.workspace_id, column.deleted_at]
  }
}
table "user_favorites" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "entity_type" {
    null = false
    type = character_varying(100)
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "is_folder" {
    null = false
    type = boolean
  }
  column "sequence" {
    null = false
    type = double_precision
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "parent_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_favorites_created_by_id_dc025309_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_favorites_parent_id_550512e4_fk_user_favorites_id" {
    columns     = [column.parent_id]
    ref_columns = [table.user_favorites.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_favorites_project_id_359b527f_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_favorites_updated_by_id_a1a5ac4a_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_favorites_user_id_cea7e2d2_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_favorites_workspace_id_aa90f680_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "fav_entity_identifier_idx" {
    columns = [column.entity_identifier]
  }
  index "fav_entity_idx" {
    columns = [column.entity_type, column.entity_identifier]
  }
  index "fav_entity_type_idx" {
    columns = [column.entity_type]
  }
  index "user_favorite_unique_entity_type_entity_identifier_user_when_de" {
    unique  = true
    columns = [column.entity_type, column.entity_identifier, column.user_id]
    where   = "(deleted_at IS NULL)"
  }
  index "user_favorites_created_by_id_dc025309" {
    columns = [column.created_by_id]
  }
  index "user_favorites_parent_id_550512e4" {
    columns = [column.parent_id]
  }
  index "user_favorites_project_id_359b527f" {
    columns = [column.project_id]
  }
  index "user_favorites_updated_by_id_a1a5ac4a" {
    columns = [column.updated_by_id]
  }
  index "user_favorites_user_id_cea7e2d2" {
    columns = [column.user_id]
  }
  index "user_favorites_workspace_id_aa90f680" {
    columns = [column.workspace_id]
  }
  unique "user_favorites_entity_type_user_id_enti_22b103ff_uniq" {
    columns = [column.entity_type, column.user_id, column.entity_identifier, column.deleted_at]
  }
}
table "user_notification_preferences" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "property_change" {
    null = false
    type = boolean
  }
  column "state_change" {
    null = false
    type = boolean
  }
  column "comment" {
    null = false
    type = boolean
  }
  column "mention" {
    null = false
    type = boolean
  }
  column "issue_completed" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = true
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_notification_pr_created_by_id_54dc743a_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_notification_pr_project_id_e0ca17f8_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_notification_pr_updated_by_id_eb70a86d_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_notification_pr_workspace_id_a2321c58_fk_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_notification_preferences_user_id_9dccc056_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_notification_preferences_created_by_id_54dc743a" {
    columns = [column.created_by_id]
  }
  index "user_notification_preferences_project_id_e0ca17f8" {
    columns = [column.project_id]
  }
  index "user_notification_preferences_updated_by_id_eb70a86d" {
    columns = [column.updated_by_id]
  }
  index "user_notification_preferences_user_id_9dccc056" {
    columns = [column.user_id]
  }
  index "user_notification_preferences_workspace_id_a2321c58" {
    columns = [column.workspace_id]
  }
}
table "user_recent_visits" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "entity_identifier" {
    null = true
    type = uuid
  }
  column "entity_name" {
    null = false
    type = character_varying(30)
  }
  column "visited_at" {
    null = false
    type = timestamptz
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_recent_visits_created_by_id_a655b75f_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_recent_visits_project_id_e5eecf27_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_recent_visits_updated_by_id_42b12ef2_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_recent_visits_user_id_f5153288_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_recent_visits_workspace_id_362a4e80_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_recent_visits_created_by_id_a655b75f" {
    columns = [column.created_by_id]
  }
  index "user_recent_visits_project_id_e5eecf27" {
    columns = [column.project_id]
  }
  index "user_recent_visits_updated_by_id_42b12ef2" {
    columns = [column.updated_by_id]
  }
  index "user_recent_visits_user_id_f5153288" {
    columns = [column.user_id]
  }
  index "user_recent_visits_workspace_id_362a4e80" {
    columns = [column.workspace_id]
  }
}
table "users" {
  schema = schema.public
  column "password" {
    null = false
    type = character_varying(128)
  }
  column "last_login" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "username" {
    null = false
    type = character_varying(128)
  }
  column "mobile_number" {
    null = true
    type = character_varying(255)
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "first_name" {
    null = false
    type = character_varying(255)
  }
  column "last_name" {
    null = false
    type = character_varying(255)
  }
  column "avatar" {
    null = false
    type = text
  }
  column "date_joined" {
    null = false
    type = timestamptz
  }
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "last_location" {
    null = false
    type = character_varying(255)
  }
  column "created_location" {
    null = false
    type = character_varying(255)
  }
  column "is_superuser" {
    null = false
    type = boolean
  }
  column "is_managed" {
    null = false
    type = boolean
  }
  column "is_password_expired" {
    null = false
    type = boolean
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "is_staff" {
    null = false
    type = boolean
  }
  column "is_email_verified" {
    null = false
    type = boolean
  }
  column "is_password_autoset" {
    null = false
    type = boolean
  }
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "user_timezone" {
    null = false
    type = character_varying(255)
  }
  column "last_active" {
    null = true
    type = timestamptz
  }
  column "last_login_time" {
    null = true
    type = timestamptz
  }
  column "last_logout_time" {
    null = true
    type = timestamptz
  }
  column "last_login_ip" {
    null = false
    type = character_varying(255)
  }
  column "last_logout_ip" {
    null = false
    type = character_varying(255)
  }
  column "last_login_medium" {
    null = false
    type = character_varying(20)
  }
  column "last_login_uagent" {
    null = false
    type = text
  }
  column "token_updated_at" {
    null = true
    type = timestamptz
  }
  column "is_bot" {
    null = false
    type = boolean
  }
  column "cover_image" {
    null = true
    type = character_varying(800)
  }
  column "display_name" {
    null = false
    type = character_varying(255)
  }
  column "avatar_asset_id" {
    null = true
    type = uuid
  }
  column "cover_image_asset_id" {
    null = true
    type = uuid
  }
  column "bot_type" {
    null = true
    type = character_varying(30)
  }
  column "is_email_valid" {
    null = false
    type = boolean
  }
  column "masked_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_avatar_asset_id_50fa2043_fk_file_assets_id" {
    columns     = [column.avatar_asset_id]
    ref_columns = [table.file_assets.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_cover_image_asset_id_b9679cbc_fk_file_assets_id" {
    columns     = [column.cover_image_asset_id]
    ref_columns = [table.file_assets.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_email_54dc62b2_like" {
    on {
      column = column.email
      ops    = varchar_pattern_ops
    }
  }
  index "user_username_cf016618_like" {
    on {
      column = column.username
      ops    = varchar_pattern_ops
    }
  }
  index "users_avatar_asset_id_50fa2043" {
    columns = [column.avatar_asset_id]
  }
  index "users_cover_image_asset_id_b9679cbc" {
    columns = [column.cover_image_asset_id]
  }
  unique "user_email_key" {
    columns = [column.email]
  }
  unique "user_username_key" {
    columns = [column.username]
  }
}
table "users_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "group_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_groups_group_id_b76f8aba_fk_auth_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.auth_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_groups_user_id_abaea130_fk_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_groups_group_id_b76f8aba" {
    columns = [column.group_id]
  }
  index "user_groups_user_id_abaea130" {
    columns = [column.user_id]
  }
  unique "user_groups_user_id_group_id_40beef00_uniq" {
    columns = [column.user_id, column.group_id]
  }
}
table "users_user_permissions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "permission_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_user_permission_permission_id_9deb68a3_fk_auth_perm" {
    columns     = [column.permission_id]
    ref_columns = [table.auth_permission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "user_user_permissions_user_id_ed4a47ea_fk_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_user_permissions_permission_id_9deb68a3" {
    columns = [column.permission_id]
  }
  index "user_user_permissions_user_id_ed4a47ea" {
    columns = [column.user_id]
  }
  unique "user_user_permissions_user_id_permission_id_7dc6e2e0_uniq" {
    columns = [column.user_id, column.permission_id]
  }
}
table "webhook_logs" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "event_type" {
    null = true
    type = character_varying(255)
  }
  column "request_method" {
    null = true
    type = character_varying(10)
  }
  column "request_headers" {
    null = true
    type = text
  }
  column "request_body" {
    null = true
    type = text
  }
  column "response_status" {
    null = true
    type = text
  }
  column "response_headers" {
    null = true
    type = text
  }
  column "response_body" {
    null = true
    type = text
  }
  column "retry_count" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "webhook" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "webhook_logs_created_by_id_71e7bc38_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "webhook_logs_updated_by_id_3d9bad04_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "webhook_logs_workspace_id_ffcd0e31_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "webhook_logs_created_by_id_71e7bc38" {
    columns = [column.created_by_id]
  }
  index "webhook_logs_updated_by_id_3d9bad04" {
    columns = [column.updated_by_id]
  }
  index "webhook_logs_workspace_id_ffcd0e31" {
    columns = [column.workspace_id]
  }
  check "webhook_logs_retry_count_check" {
    expr = "(retry_count >= 0)"
  }
}
table "webhooks" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "url" {
    null = false
    type = character_varying(1024)
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "secret_key" {
    null = false
    type = character_varying(255)
  }
  column "project" {
    null = false
    type = boolean
  }
  column "issue" {
    null = false
    type = boolean
  }
  column "module" {
    null = false
    type = boolean
  }
  column "cycle" {
    null = false
    type = boolean
  }
  column "issue_comment" {
    null = false
    type = boolean
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "is_internal" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "webhooks_created_by_id_25aca1b0_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "webhooks_updated_by_id_ea35154e_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "webhooks_workspace_id_da5865d7_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "webhook_url_unique_url_when_deleted_at_null" {
    unique  = true
    columns = [column.workspace_id, column.url]
    where   = "(deleted_at IS NULL)"
  }
  index "webhooks_created_by_id_25aca1b0" {
    columns = [column.created_by_id]
  }
  index "webhooks_updated_by_id_ea35154e" {
    columns = [column.updated_by_id]
  }
  index "webhooks_workspace_id_da5865d7" {
    columns = [column.workspace_id]
  }
  unique "webhooks_workspace_id_url_deleted_at_ea7a1429_uniq" {
    columns = [column.workspace_id, column.url, column.deleted_at]
  }
}
table "workspace_home_preferences" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "is_enabled" {
    null = false
    type = boolean
  }
  column "config" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_home_prefe_workspace_id_b49f76e0_fk_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_home_preferences_created_by_id_f31fc163_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_home_preferences_updated_by_id_14ed118a_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_home_preferences_user_id_4087938d_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_home_preferences_created_by_id_f31fc163" {
    columns = [column.created_by_id]
  }
  index "workspace_home_preferences_updated_by_id_14ed118a" {
    columns = [column.updated_by_id]
  }
  index "workspace_home_preferences_user_id_4087938d" {
    columns = [column.user_id]
  }
  index "workspace_home_preferences_workspace_id_b49f76e0" {
    columns = [column.workspace_id]
  }
  index "workspace_user_home_preferences_unique_workspace_user_key_when_" {
    unique  = true
    columns = [column.workspace_id, column.user_id, column.key]
    where   = "(deleted_at IS NULL)"
  }
  unique "workspace_home_preferenc_workspace_id_user_id_key_75ea36d3_uniq" {
    columns = [column.workspace_id, column.user_id, column.key, column.deleted_at]
  }
}
table "workspace_integrations" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "config" {
    null = false
    type = jsonb
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "api_token_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "integration_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_integratio_integration_id_6cb0aace_fk_integrati" {
    columns     = [column.integration_id]
    ref_columns = [table.integrations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_integrations_actor_id_21619aa1_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_integrations_api_token_id_bdb1759b_fk_api_tokens_id" {
    columns     = [column.api_token_id]
    ref_columns = [table.api_tokens.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_integrations_created_by_id_37639c73_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_integrations_updated_by_id_fce01dcb_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_integrations_workspace_id_27ebeb6b_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_integrations_actor_id_21619aa1" {
    columns = [column.actor_id]
  }
  index "workspace_integrations_api_token_id_bdb1759b" {
    columns = [column.api_token_id]
  }
  index "workspace_integrations_created_by_id_37639c73" {
    columns = [column.created_by_id]
  }
  index "workspace_integrations_integration_id_6cb0aace" {
    columns = [column.integration_id]
  }
  index "workspace_integrations_updated_by_id_fce01dcb" {
    columns = [column.updated_by_id]
  }
  index "workspace_integrations_workspace_id_27ebeb6b" {
    columns = [column.workspace_id]
  }
  unique "workspace_integrations_workspace_id_integration_fa041c22_uniq" {
    columns = [column.workspace_id, column.integration_id]
  }
}
table "workspace_member_invites" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "email" {
    null = false
    type = character_varying(255)
  }
  column "accepted" {
    null = false
    type = boolean
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "message" {
    null = true
    type = text
  }
  column "responded_at" {
    null = true
    type = timestamptz
  }
  column "role" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_member_invite_created_by_id_082f21d3_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_member_invite_updated_by_id_d31a9c7f_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_member_invite_workspace_id_d935b364_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_member_invite_created_by_id_082f21d3" {
    columns = [column.created_by_id]
  }
  index "workspace_member_invite_unique_email_workspace_when_deleted_at_" {
    unique  = true
    columns = [column.email, column.workspace_id]
    where   = "(deleted_at IS NULL)"
  }
  index "workspace_member_invite_updated_by_id_d31a9c7f" {
    columns = [column.updated_by_id]
  }
  index "workspace_member_invite_workspace_id_d935b364" {
    columns = [column.workspace_id]
  }
  check "workspace_member_invite_role_check" {
    expr = "(role >= 0)"
  }
  unique "workspace_member_invites_email_workspace_id_delet_2f03573e_uniq" {
    columns = [column.email, column.workspace_id, column.deleted_at]
  }
}
table "workspace_members" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "role" {
    null = false
    type = smallint
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "member_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "company_role" {
    null = true
    type = text
  }
  column "view_props" {
    null = false
    type = jsonb
  }
  column "default_props" {
    null = false
    type = jsonb
  }
  column "issue_props" {
    null = false
    type = jsonb
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_member_created_by_id_8dc8b040_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_member_member_id_824f5497_fk_user_id" {
    columns     = [column.member_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_member_updated_by_id_1cec0062_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_member_workspace_id_33f66d4b_fk_workspace_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_member_created_by_id_8dc8b040" {
    columns = [column.created_by_id]
  }
  index "workspace_member_member_id_824f5497" {
    columns = [column.member_id]
  }
  index "workspace_member_unique_workspace_member_when_deleted_at_null" {
    unique  = true
    columns = [column.workspace_id, column.member_id]
    where   = "(deleted_at IS NULL)"
  }
  index "workspace_member_updated_by_id_1cec0062" {
    columns = [column.updated_by_id]
  }
  index "workspace_member_workspace_id_33f66d4b" {
    columns = [column.workspace_id]
  }
  check "workspace_member_role_check" {
    expr = "(role >= 0)"
  }
  unique "workspace_members_workspace_id_member_id_d_d7bfa872_uniq" {
    columns = [column.workspace_id, column.member_id, column.deleted_at]
  }
}
table "workspace_themes" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(300)
  }
  column "colors" {
    null = false
    type = jsonb
  }
  column "actor_id" {
    null = false
    type = uuid
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_themes_actor_id_0e94172e_fk_users_id" {
    columns     = [column.actor_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_themes_created_by_id_676e2655_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_themes_updated_by_id_bba863fe_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_themes_workspace_id_d1bffad8_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_theme_unique_workspace_name_when_deleted_at_null" {
    unique  = true
    columns = [column.workspace_id, column.name]
    where   = "(deleted_at IS NULL)"
  }
  index "workspace_themes_actor_id_0e94172e" {
    columns = [column.actor_id]
  }
  index "workspace_themes_created_by_id_676e2655" {
    columns = [column.created_by_id]
  }
  index "workspace_themes_updated_by_id_bba863fe" {
    columns = [column.updated_by_id]
  }
  index "workspace_themes_workspace_id_d1bffad8" {
    columns = [column.workspace_id]
  }
  unique "workspace_themes_workspace_id_name_deleted_at_b536ffd3_uniq" {
    columns = [column.workspace_id, column.name, column.deleted_at]
  }
}
table "workspace_user_links" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = true
    type = character_varying(255)
  }
  column "url" {
    null = false
    type = text
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owner_id" {
    null = false
    type = uuid
  }
  column "project_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_user_links_created_by_id_b9ce7a5d_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_links_owner_id_37d99444_fk_users_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_links_project_id_045e0d53_fk_projects_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_links_updated_by_id_bd0b017f_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_links_workspace_id_1b0a8e22_fk_workspaces_id" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_user_links_created_by_id_b9ce7a5d" {
    columns = [column.created_by_id]
  }
  index "workspace_user_links_owner_id_37d99444" {
    columns = [column.owner_id]
  }
  index "workspace_user_links_project_id_045e0d53" {
    columns = [column.project_id]
  }
  index "workspace_user_links_updated_by_id_bd0b017f" {
    columns = [column.updated_by_id]
  }
  index "workspace_user_links_workspace_id_1b0a8e22" {
    columns = [column.workspace_id]
  }
}
table "workspace_user_preferences" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "is_pinned" {
    null = false
    type = boolean
  }
  column "sort_order" {
    null = false
    type = double_precision
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_user_prefe_workspace_id_a345adde_fk_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_preferences_created_by_id_2d566570_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_preferences_updated_by_id_65fed266_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_preferences_user_id_0ba5007a_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_user_preferences_created_by_id_2d566570" {
    columns = [column.created_by_id]
  }
  index "workspace_user_preferences_unique_workspace_user_key_when_delet" {
    unique  = true
    columns = [column.workspace_id, column.user_id, column.key]
    where   = "(deleted_at IS NULL)"
  }
  index "workspace_user_preferences_updated_by_id_65fed266" {
    columns = [column.updated_by_id]
  }
  index "workspace_user_preferences_user_id_0ba5007a" {
    columns = [column.user_id]
  }
  index "workspace_user_preferences_workspace_id_a345adde" {
    columns = [column.workspace_id]
  }
  unique "workspace_user_preferenc_workspace_id_user_id_key_79341493_uniq" {
    columns = [column.workspace_id, column.user_id, column.key, column.deleted_at]
  }
}
table "workspace_user_properties" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "filters" {
    null = false
    type = jsonb
  }
  column "display_filters" {
    null = false
    type = jsonb
  }
  column "display_properties" {
    null = false
    type = jsonb
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "user_id" {
    null = false
    type = uuid
  }
  column "workspace_id" {
    null = false
    type = uuid
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "rich_filters" {
    null = false
    type = jsonb
  }
  column "navigation_control_preference" {
    null = false
    type = character_varying(25)
  }
  column "navigation_project_limit" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_user_prope_workspace_id_1dc3e2a6_fk_workspace" {
    columns     = [column.workspace_id]
    ref_columns = [table.workspaces.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_properties_created_by_id_6d8d1c4e_fk_users_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_properties_updated_by_id_910a2cc5_fk_users_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_user_properties_user_id_b1079e07_fk_users_id" {
    columns     = [column.user_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_user_properties_created_by_id_6d8d1c4e" {
    columns = [column.created_by_id]
  }
  index "workspace_user_properties_unique_workspace_user_when_deleted_at" {
    unique  = true
    columns = [column.workspace_id, column.user_id]
    where   = "(deleted_at IS NULL)"
  }
  index "workspace_user_properties_updated_by_id_910a2cc5" {
    columns = [column.updated_by_id]
  }
  index "workspace_user_properties_user_id_b1079e07" {
    columns = [column.user_id]
  }
  index "workspace_user_properties_workspace_id_1dc3e2a6" {
    columns = [column.workspace_id]
  }
  unique "workspace_user_propertie_workspace_id_user_id_del_a7cf15bc_uniq" {
    columns = [column.workspace_id, column.user_id, column.deleted_at]
  }
}
table "workspaces" {
  schema = schema.public
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = false
    type = timestamptz
  }
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(80)
  }
  column "logo" {
    null = true
    type = text
  }
  column "slug" {
    null = false
    type = character_varying(48)
  }
  column "created_by_id" {
    null = true
    type = uuid
  }
  column "owner_id" {
    null = false
    type = uuid
  }
  column "updated_by_id" {
    null = true
    type = uuid
  }
  column "organization_size" {
    null = true
    type = character_varying(20)
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  column "logo_asset_id" {
    null = true
    type = uuid
  }
  column "timezone" {
    null = false
    type = character_varying(255)
  }
  column "background_color" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "workspace_created_by_id_10ad894e_fk_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_owner_id_60a8bafc_fk_user_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspace_updated_by_id_09d249ed_fk_user_id" {
    columns     = [column.updated_by_id]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "workspaces_logo_asset_id_a784bb00_fk_file_assets_id" {
    columns     = [column.logo_asset_id]
    ref_columns = [table.file_assets.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "workspace_created_by_id_10ad894e" {
    columns = [column.created_by_id]
  }
  index "workspace_owner_id_60a8bafc" {
    columns = [column.owner_id]
  }
  index "workspace_slug_4d89d459_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "workspace_updated_by_id_09d249ed" {
    columns = [column.updated_by_id]
  }
  index "workspaces_logo_asset_id_a784bb00" {
    columns = [column.logo_asset_id]
  }
  unique "workspace_slug_key" {
    columns = [column.slug]
  }
}
schema "public" {
  comment = "standard public schema"
}
