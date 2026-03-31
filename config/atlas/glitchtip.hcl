Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "account_emailaddress" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "verified" {
    null = false
    type = boolean
  }
  column "primary" {
    null = false
    type = boolean
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "account_emailaddress_user_id_2c513194_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "account_emailaddress_email_03be32b2" {
    columns = [column.email]
  }
  index "account_emailaddress_email_03be32b2_like" {
    on {
      column = column.email
      ops    = varchar_pattern_ops
    }
  }
  index "account_emailaddress_user_id_2c513194" {
    columns = [column.user_id]
  }
  index "unique_primary_email" {
    unique  = true
    columns = [column.user_id, column.primary]
    where   = "\"primary\""
  }
  index "unique_verified_email" {
    unique  = true
    columns = [column.email]
    where   = "verified"
  }
  unique "account_emailaddress_user_id_email_987c8728_uniq" {
    columns = [column.user_id, column.email]
  }
}
table "account_emailconfirmation" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "sent" {
    null = true
    type = timestamptz
  }
  column "key" {
    null = false
    type = character_varying(64)
  }
  column "email_address_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "account_emailconfirm_email_address_id_5b7f8c58_fk_account_e" {
    columns     = [column.email_address_id]
    ref_columns = [table.account_emailaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "account_emailconfirmation_email_address_id_5b7f8c58" {
    columns = [column.email_address_id]
  }
  index "account_emailconfirmation_key_f43612bd_like" {
    on {
      column = column.key
      ops    = varchar_pattern_ops
    }
  }
  unique "account_emailconfirmation_key_key" {
    columns = [column.key]
  }
}
table "alerts_alertrecipient" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "recipient_type" {
    null = false
    type = character_varying(16)
  }
  column "url" {
    null = false
    type = character_varying(2000)
  }
  column "alert_id" {
    null = false
    type = bigint
  }
  column "tags_to_add" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "config" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "alerts_alertrecipien_alert_id_e751a912_fk_alerts_pr" {
    columns     = [column.alert_id]
    ref_columns = [table.alerts_projectalert.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "alerts_alertrecipient_alert_id_e751a912" {
    columns = [column.alert_id]
  }
  unique "alerts_alertrecipient_alert_id_recipient_type_url_afe81d2e_uniq" {
    columns = [column.alert_id, column.recipient_type, column.url]
  }
}
table "alerts_notification" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "is_sent" {
    null = false
    type = boolean
  }
  column "project_alert_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "alerts_notification_project_alert_id_26a4df64_fk_alerts_pr" {
    columns     = [column.project_alert_id]
    ref_columns = [table.alerts_projectalert.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "alerts_notification_created_4bb1977b" {
    columns = [column.created]
  }
  index "alerts_notification_project_alert_id_26a4df64" {
    columns = [column.project_alert_id]
  }
}
table "alerts_notification_issues" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "notification_id" {
    null = false
    type = bigint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "alerts_notification__issue_id_19caaee3_fk_issue_eve" {
    columns     = [column.issue_id]
    ref_columns = [table.issue_events_issue.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "alerts_notification__notification_id_abfc7da3_fk_alerts_no" {
    columns     = [column.notification_id]
    ref_columns = [table.alerts_notification.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "alerts_notification_issues_issue_id_19caaee3" {
    columns = [column.issue_id]
  }
  index "alerts_notification_issues_notification_id_abfc7da3" {
    columns = [column.notification_id]
  }
  unique "alerts_notification_issu_notification_id_issue_id_68701830_uniq" {
    columns = [column.notification_id, column.issue_id]
  }
}
table "alerts_projectalert" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "timespan_minutes" {
    null = true
    type = smallint
  }
  column "quantity" {
    null = true
    type = smallint
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "uptime" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "alerts_projectalert_project_id_d72e26b7_fk_projects_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "alerts_projectalert_created_2fc73449" {
    columns = [column.created]
  }
  index "alerts_projectalert_project_id_d72e26b7" {
    columns = [column.project_id]
  }
  check "alerts_projectalert_quantity_check" {
    expr = "(quantity >= 0)"
  }
  check "alerts_projectalert_timespan_minutes_check" {
    expr = "(timespan_minutes >= 0)"
  }
}
table "api_tokens_apitoken" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "label" {
    null = false
    type = character_varying(255)
  }
  column "scopes" {
    null = false
    type = bigint
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "api_tokens_apitoken_user_id_92435ca3_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "api_tokens_apitoken_created_dff90883" {
    columns = [column.created]
  }
  index "api_tokens_apitoken_token_5d2d2d5d_like" {
    on {
      column = column.token
      ops    = varchar_pattern_ops
    }
  }
  index "api_tokens_apitoken_user_id_92435ca3" {
    columns = [column.user_id]
  }
  unique "api_tokens_apitoken_token_key" {
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
table "difs_debuginformationfile" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "name" {
    null = false
    type = text
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "difs_debuginformatio_project_id_98b3bcff_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "difs_debuginformationfile_file_id_0f375ae8_fk_files_file_id" {
    columns     = [column.file_id]
    ref_columns = [table.files_file.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "difs_debugi_project_99cec2_idx" {
    columns = [column.project_id, column.file_id]
  }
  index "difs_debuginformationfile_created_a0e5f2b4" {
    columns = [column.created]
  }
  index "difs_debuginformationfile_file_id_0f375ae8" {
    columns = [column.file_id]
  }
  index "difs_debuginformationfile_project_id_98b3bcff" {
    columns = [column.project_id]
  }
}
table "django_admin_log" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "action_time" {
    null = false
    type = timestamptz
  }
  column "object_id" {
    null = true
    type = text
  }
  column "object_repr" {
    null = false
    type = character_varying(200)
  }
  column "action_flag" {
    null = false
    type = smallint
  }
  column "change_message" {
    null = false
    type = text
  }
  column "content_type_id" {
    null = true
    type = integer
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "django_admin_log_content_type_id_c4bce8eb_fk_django_co" {
    columns     = [column.content_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "django_admin_log_user_id_c564eba6_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "django_admin_log_content_type_id_c4bce8eb" {
    columns = [column.content_type_id]
  }
  index "django_admin_log_user_id_c564eba6" {
    columns = [column.user_id]
  }
  check "django_admin_log_action_flag_check" {
    expr = "(action_flag >= 0)"
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
table "environments_environment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "environments_environ_organization_id_5e73e9d7_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "environments_environment_created_68e37d5a" {
    columns = [column.created]
  }
  index "environments_environment_organization_id_5e73e9d7" {
    columns = [column.organization_id]
  }
  unique "environments_environment_organization_id_name_e04cf45d_uniq" {
    columns = [column.organization_id, column.name]
  }
}
table "environments_environmentproject" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "is_hidden" {
    null = false
    type = boolean
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "environment_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "environments_environ_environment_id_4b61b449_fk_environme" {
    columns     = [column.environment_id]
    ref_columns = [table.environments_environment.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "environments_environ_project_id_f1b49983_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "environments_environmentproject_environment_id_4b61b449_fk" {
    columns     = [column.environment_id]
    ref_columns = [table.environments_environment.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "environments_environmentproject_created_33629df1" {
    columns = [column.created]
  }
  index "environments_environmentproject_environment_id_4b61b449" {
    columns = [column.environment_id]
  }
  index "environments_environmentproject_project_id_f1b49983" {
    columns = [column.project_id]
  }
  unique "environments_environment_project_id_environment_i_435ad371_uniq" {
    columns = [column.project_id, column.environment_id]
  }
}
table "files_file" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "name" {
    null = false
    type = text
  }
  column "headers" {
    null = true
    type = jsonb
  }
  column "size" {
    null = false
    type = integer
  }
  column "checksum" {
    null = true
    type = character_varying(40)
  }
  column "type" {
    null = false
    type = character_varying(64)
  }
  column "blob_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "files_file_blob_id_ac0e8c7e_fk_files_fileblob_id" {
    columns     = [column.blob_id]
    ref_columns = [table.files_fileblob.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "files_file_blob_id_ac0e8c7e" {
    columns = [column.blob_id]
  }
  index "files_file_checksum_cfc180a4" {
    columns = [column.checksum]
  }
  index "files_file_checksum_cfc180a4_like" {
    on {
      column = column.checksum
      ops    = varchar_pattern_ops
    }
  }
  index "files_file_created_f8bb89d7" {
    columns = [column.created]
  }
  check "files_file_size_check" {
    expr = "(size >= 0)"
  }
}
table "files_fileblob" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "checksum" {
    null = false
    type = character_varying(40)
  }
  column "size" {
    null = true
    type = integer
  }
  column "blob" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  index "files_fileblob_checksum_fd4ecd13_like" {
    on {
      column = column.checksum
      ops    = varchar_pattern_ops
    }
  }
  index "files_fileblob_created_e897448a" {
    columns = [column.created]
  }
  check "files_fileblob_size_check" {
    expr = "(size >= 0)"
  }
  unique "files_fileblob_checksum_key" {
    columns = [column.checksum]
  }
}
table "issue_events_comment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "text" {
    null = true
    type = text
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_events_comment_issue_id_a6014886_fk_issue_events_issue_id" {
    columns     = [column.issue_id]
    ref_columns = [table.issue_events_issue.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_comment_user_id_947a468b_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_events_comment_issue_id_a6014886" {
    columns = [column.issue_id]
  }
  index "issue_events_comment_user_id_947a468b" {
    columns = [column.user_id]
  }
}
table "issue_events_issue" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "is_deleted" {
    null = false
    type = boolean
  }
  column "culprit" {
    null = true
    type = character_varying(1024)
  }
  column "is_public" {
    null = false
    type = boolean
  }
  column "level" {
    null = false
    type = smallint
  }
  column "metadata" {
    null = false
    type = jsonb
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = smallint
  }
  column "status" {
    null = false
    type = smallint
  }
  column "short_id" {
    null = true
    type = integer
  }
  column "search_vector" {
    null = false
    type = tsvector
  }
  column "count" {
    null = false
    type = integer
  }
  column "first_seen" {
    null = false
    type = timestamptz
  }
  column "last_seen" {
    null = false
    type = timestamptz
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "first_release_id" {
    null = true
    type = bigint
  }
  column "last_release_id" {
    null = true
    type = bigint
  }
  column "resolved_in_release_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_events_issue_first_release_id_77989250_fk_releases_" {
    columns     = [column.first_release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_issue_last_release_id_69bcb4e7_fk_releases_" {
    columns     = [column.last_release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_issue_project_id_285e6462_fk_projects_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_issue_resolved_in_release__01e36a7b_fk_releases_" {
    columns     = [column.resolved_in_release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_event_search__346c17_gin" {
    columns = [column.search_vector]
    type    = GIN
  }
  index "issue_events_issue_first_release_id_77989250" {
    columns = [column.first_release_id]
  }
  index "issue_events_issue_first_seen_10805fb9" {
    columns = [column.first_seen]
  }
  index "issue_events_issue_last_release_id_69bcb4e7" {
    columns = [column.last_release_id]
  }
  index "issue_events_issue_last_seen_2f5857cf" {
    columns = [column.last_seen]
  }
  index "issue_events_issue_project_id_285e6462" {
    columns = [column.project_id]
  }
  index "issue_events_issue_resolved_in_release_id_01e36a7b" {
    columns = [column.resolved_in_release_id]
  }
  index "issue_title_trgm_idx" {
    type = GIN
    on {
      column = column.title
      ops    = gin_trgm_ops
    }
  }
  check "issue_events_issue_count_check" {
    expr = "(count >= 0)"
  }
  check "issue_events_issue_level_check" {
    expr = "(level >= 0)"
  }
  check "issue_events_issue_short_id_check" {
    expr = "(short_id >= 0)"
  }
  check "issue_events_issue_status_check" {
    expr = "(status >= 0)"
  }
  check "issue_events_issue_type_check" {
    expr = "(type >= 0)"
  }
  unique "project_short_id_unique" {
    columns = [column.project_id, column.short_id]
  }
}
table "issue_events_issueaggregate" {
  schema = schema.public
  column "issue_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.issue_id, column.organization_id, column.date]
  }
  foreign_key "issue_events_issueaggregate_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "issue_events_issueaggregate_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "issue_events_issueevent" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v7()")
  }
  column "event_id" {
    null = true
    type = uuid
  }
  column "timestamp" {
    null = false
    type = timestamptz
  }
  column "created" {
    null    = false
    type    = timestamptz
    default = sql("timezone('utc'::text, now())")
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "release_id" {
    null = true
    type = bigint
  }
  column "type" {
    null    = false
    type    = smallint
    default = 0
  }
  column "level" {
    null    = false
    type    = smallint
    default = 4
  }
  column "title" {
    null = false
    type = character_varying(255)
  }
  column "transaction" {
    null = false
    type = character_varying(1024)
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "tags" {
    null = false
    type = jsonb
  }
  column "hashes" {
    null    = false
    type    = sql("text[]")
    default = sql("ARRAY[]::text[]")
  }
  primary_key {
    columns = [column.id, column.organization_id]
  }
  foreign_key "issue_events_issueevent_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "issue_events_issueevent_release_id_fkey" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "issueevent_event_id_idx" {
    columns = [column.event_id]
    where   = "(event_id IS NOT NULL)"
  }
  index "issueevent_hashes_idx" {
    columns = [column.hashes]
    type    = GIN
  }
  index "issueevent_issue_id_idx" {
    on {
      column = column.issue_id
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "issueevent_release_idx" {
    columns = [column.release_id]
  }
  check "issue_events_issueevent_level_check" {
    expr = "((level >= 0) AND (level <= 5))"
  }
  check "issue_events_issueevent_type_check" {
    expr = "(type >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.id]
  }
}
table "issue_events_issuehash" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "value" {
    null = false
    type = uuid
  }
  column "issue_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_events_issueha_issue_id_a5551eef_fk_issue_eve" {
    columns     = [column.issue_id]
    ref_columns = [table.issue_events_issue.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_issueha_project_id_554528c6_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_events_issuehash_issue_id_a5551eef" {
    columns = [column.issue_id]
  }
  index "issue_events_issuehash_project_id_554528c6" {
    columns = [column.project_id]
  }
  index "issue_events_issuehash_value_15589000" {
    columns = [column.value]
  }
  unique "issue hash project" {
    columns = [column.project_id, column.value]
  }
}
table "issue_events_issuetag" {
  schema = schema.public
  column "issue_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "tag_key_id" {
    null = false
    type = integer
  }
  column "tag_value_id" {
    null = false
    type = integer
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.issue_id, column.organization_id, column.tag_key_id, column.tag_value_id, column.date]
  }
  foreign_key "issue_events_issuetag_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "issue_events_issuetag_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "issue_events_tagkey" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "issue_events_tagkey_key_186354a4_like" {
    on {
      column = column.key
      ops    = varchar_pattern_ops
    }
  }
  unique "issue_events_tagkey_key_key" {
    columns = [column.key]
  }
}
table "issue_events_tagvalue" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "value" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  unique "issue_events_tagvalue_unique_value" {
    columns = [column.value]
  }
}
table "issue_events_userreport" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "event_id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "comments" {
    null = false
    type = text
  }
  column "issue_id" {
    null = true
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "issue_events_userrep_issue_id_df1edb5f_fk_issue_eve" {
    columns     = [column.issue_id]
    ref_columns = [table.issue_events_issue.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "issue_events_userrep_project_id_76d2cbb8_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "issue_events_userreport_created_b4fc70ce" {
    columns = [column.created]
  }
  index "issue_events_userreport_issue_id_df1edb5f" {
    columns = [column.issue_id]
  }
  index "issue_events_userreport_project_id_76d2cbb8" {
    columns = [column.project_id]
  }
  unique "project_event_unique" {
    columns = [column.project_id, column.event_id]
  }
}
table "logs_logevent" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "trace_id" {
    null = true
    type = uuid
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "span_id" {
    null = true
    type = bigint
  }
  column "level" {
    null    = false
    type    = smallint
    default = 2
  }
  column "severity_number" {
    null = true
    type = smallint
  }
  column "body" {
    null = false
    type = text
  }
  column "service" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "environment" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "host" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "data" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  primary_key {
    columns = [column.id, column.organization_id]
  }
  foreign_key "logs_logevent_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "logs_logevent_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "logevent_body_trgm_idx" {
    type = GIN
    on {
      column = column.body
      ops    = gin_trgm_ops
    }
  }
  index "logevent_org_env_idx" {
    on {
      column = column.organization_id
    }
    on {
      column = column.environment
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_org_host_idx" {
    on {
      column = column.organization_id
    }
    on {
      column = column.host
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_org_id_idx" {
    on {
      column = column.organization_id
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_org_level_idx" {
    on {
      column = column.organization_id
    }
    on {
      column = column.level
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_org_svc_idx" {
    on {
      column = column.organization_id
    }
    on {
      column = column.service
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_proj_id_idx" {
    on {
      column = column.project_id
    }
    on {
      desc   = true
      column = column.id
    }
  }
  index "logevent_trace_id_idx" {
    columns = [column.trace_id]
    where   = "(trace_id IS NOT NULL)"
  }
  check "logs_logevent_level_check" {
    expr = "((level >= 0) AND (level <= 5))"
  }
  check "logs_logevent_severity_check" {
    expr = "((severity_number IS NULL) OR ((severity_number >= 1) AND (severity_number <= 24)))"
  }
  partition {
    type    = RANGE
    columns = [column.id]
  }
}
table "logs_logresource" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(20)
  }
  column "first_seen" {
    null = false
    type = timestamptz
  }
  column "last_seen" {
    null = false
    type = timestamptz
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "logs_logresource_organization_id_3b564c22_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "logresource_org_type_idx" {
    columns = [column.organization_id, column.type]
  }
  index "logs_logresource_organization_id_3b564c22" {
    columns = [column.organization_id]
  }
  unique "unique_org_resource" {
    columns = [column.organization_id, column.name, column.type]
  }
}
table "mfa_authenticator" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "type" {
    null = false
    type = character_varying(20)
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "last_used_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "mfa_authenticator_user_id_0c3a50c0_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "mfa_authenticator_user_id_0c3a50c0" {
    columns = [column.user_id]
  }
  index "unique_authenticator_type" {
    unique  = true
    columns = [column.user_id, column.type]
    where   = "((type)::text = ANY ((ARRAY['totp'::character varying, 'recovery_codes'::character varying])::text[]))"
  }
}
table "oauth_oauthapplication" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "client_id" {
    null = false
    type = character_varying(255)
  }
  column "client_secret" {
    null = false
    type = character_varying(255)
  }
  column "client_id_issued_at" {
    null = false
    type = integer
  }
  column "client_secret_expires_at" {
    null = true
    type = integer
  }
  column "client_info" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "oauth_oauthapplication_client_id_35140444_like" {
    on {
      column = column.client_id
      ops    = varchar_pattern_ops
    }
  }
  index "oauth_oauthapplication_created_bcb5bb1c" {
    columns = [column.created]
  }
  unique "oauth_oauthapplication_client_id_key" {
    columns = [column.client_id]
  }
}
table "oauth_oauthrefreshtoken" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "access_token_key" {
    null = false
    type = character_varying(64)
  }
  column "scopes" {
    null = false
    type = text
  }
  column "expires_at" {
    null = true
    type = integer
  }
  column "is_revoked" {
    null = false
    type = boolean
  }
  column "application_id" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "oauth_oauthrefreshto_application_id_61c87286_fk_oauth_oau" {
    columns     = [column.application_id]
    ref_columns = [table.oauth_oauthapplication.column.client_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "oauth_oauthrefreshtoken_user_id_2d6b28b6_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "oauth_oauthrefreshtoken_application_id_61c87286" {
    columns = [column.application_id]
  }
  index "oauth_oauthrefreshtoken_application_id_61c87286_like" {
    on {
      column = column.application_id
      ops    = varchar_pattern_ops
    }
  }
  index "oauth_oauthrefreshtoken_created_b2d16737" {
    columns = [column.created]
  }
  index "oauth_oauthrefreshtoken_token_508b7548_like" {
    on {
      column = column.token
      ops    = varchar_pattern_ops
    }
  }
  index "oauth_oauthrefreshtoken_user_id_2d6b28b6" {
    columns = [column.user_id]
  }
  unique "oauth_oauthrefreshtoken_token_key" {
    columns = [column.token]
  }
}
table "organizations_ext_organization" {
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
  column "is_active" {
    null = false
    type = boolean
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "modified" {
    null = false
    type = timestamptz
  }
  column "slug" {
    null = false
    type = character_varying(200)
  }
  column "is_accepting_events" {
    null = false
    type = boolean
  }
  column "open_membership" {
    null = false
    type = boolean
  }
  column "scrub_ip_addresses" {
    null = false
    type = boolean
  }
  column "event_throttle_rate" {
    null = false
    type = smallint
  }
  column "stripe_customer_id" {
    null = false
    type = character_varying(28)
  }
  column "stripe_primary_subscription_id" {
    null = true
    type = character_varying(30)
  }
  column "is_deleted" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organizations_ext_or_stripe_primary_subsc_2de96c0b_fk_stripe_st" {
    columns     = [column.stripe_primary_subscription_id]
    ref_columns = [table.stripe_stripesubscription.column.stripe_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "organizations_ext_organi_stripe_primary_subscript_2de96c0b_like" {
    on {
      column = column.stripe_primary_subscription_id
      ops    = varchar_pattern_ops
    }
  }
  index "organizations_ext_organiza_stripe_primary_subscriptio_2de96c0b" {
    columns = [column.stripe_primary_subscription_id]
  }
  index "organizations_ext_organization_slug_5a7a61c9_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "organizations_ext_organization_event_throttle_rate_check" {
    expr = "(event_throttle_rate >= 0)"
  }
  unique "organizations_ext_organization_slug_key" {
    columns = [column.slug]
  }
}
table "organizations_ext_organizationinvitation" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "guid" {
    null = false
    type = uuid
  }
  column "invitee_identifier" {
    null = false
    type = character_varying(1000)
  }
  column "invited_by_id" {
    null = false
    type = bigint
  }
  column "invitee_id" {
    null = true
    type = bigint
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organizations_ext_or_invited_by_id_35eeb92a_fk_users_use" {
    columns     = [column.invited_by_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "organizations_ext_or_invitee_id_9a400689_fk_users_use" {
    columns     = [column.invitee_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "organizations_ext_organiz_organization_id_d6f74ca6_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "organizations_ext_organiza_organization_id_d6f74ca6" {
    columns = [column.organization_id]
  }
  index "organizations_ext_organizationinvitation_invited_by_id_35eeb92a" {
    columns = [column.invited_by_id]
  }
  index "organizations_ext_organizationinvitation_invitee_id_9a400689" {
    columns = [column.invitee_id]
  }
}
table "organizations_ext_organizationowner" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "organization_user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organizations_ext_or_organization_user_id_d9d30739_fk_organizat" {
    columns     = [column.organization_user_id]
    ref_columns = [table.organizations_ext_organizationuser.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "organizations_ext_organizationowner_organization_id_1baaa212_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "organizations_ext_organizationowner_organization_id_key" {
    columns = [column.organization_id]
  }
  unique "organizations_ext_organizationowner_organization_user_id_key" {
    columns = [column.organization_user_id]
  }
}
table "organizations_ext_organizationsocialapp" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "social_app_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organizations_ext_or_social_app_id_1c589308_fk_socialacc" {
    columns     = [column.social_app_id]
    ref_columns = [table.socialaccount_socialapp.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "organizations_ext_organiz_organization_id_6b8c2278_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "organizations_ext_organiza_organization_id_6b8c2278" {
    columns = [column.organization_id]
  }
  unique "organizations_ext_organizationsocialapp_social_app_id_key" {
    columns = [column.social_app_id]
  }
}
table "organizations_ext_organizationuser" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "modified" {
    null = false
    type = timestamptz
  }
  column "role" {
    null = false
    type = smallint
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "email" {
    null = true
    type = character_varying(254)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "organizations_ext_or_user_id_d255140d_fk_users_use" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "organizations_ext_organizationuser_organization_id_f5a7ee4a_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "organizations_ext_organizationuser_organization_id_f5a7ee4a" {
    columns = [column.organization_id]
  }
  index "organizations_ext_organizationuser_user_id_d255140d" {
    columns = [column.user_id]
  }
  check "organizations_ext_organizationuser_role_check" {
    expr = "(role >= 0)"
  }
  unique "organizations_ext_organi_email_organization_id_22b69941_uniq" {
    columns = [column.email, column.organization_id]
  }
  unique "organizations_ext_organi_user_id_organization_id_60b380fc_uniq" {
    columns = [column.user_id, column.organization_id]
  }
}
table "performance_spanstaging" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "duration" {
    null = false
    type = double_precision
  }
  column "timestamp" {
    null = false
    type = timestamptz
  }
  column "transaction_name" {
    null = false
    type = character_varying(1024)
  }
  column "span_id" {
    null = false
    type = character_varying(32)
  }
  column "transaction_id" {
    null = false
    type = character_varying(32)
  }
  column "op" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null    = false
    type    = character_varying(500)
    default = ""
  }
  primary_key {
    columns = [column.id, column.organization_id]
  }
  partition {
    type    = RANGE
    columns = [column.id]
  }
}
table "performance_transactiongroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = integer
  }
  column "transaction" {
    null = false
    type = character_varying(1024)
  }
  column "op" {
    null = false
    type = character_varying(255)
  }
  column "method" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "created" {
    null    = false
    type    = timestamptz
    default = sql("now()")
  }
  column "first_seen" {
    null = false
    type = timestamptz
  }
  column "last_seen" {
    null = false
    type = timestamptz
  }
  column "avg_duration" {
    null    = false
    type    = double_precision
    default = 0
  }
  column "p50" {
    null = true
    type = double_precision
  }
  column "p95" {
    null = true
    type = double_precision
  }
  column "count" {
    null    = false
    type    = bigint
    default = 0
  }
  column "error_count" {
    null    = false
    type    = bigint
    default = 0
  }
  column "duration_histogram" {
    null    = false
    type    = sql("integer[]")
    default = sql("array_fill(0, ARRAY[50])")
  }
  primary_key {
    columns = [column.id, column.organization_id]
  }
  index "perf_txgroup_org_lastseen" {
    columns = [column.organization_id, column.last_seen]
  }
  index "performance_transactiongroup_created" {
    columns = [column.created]
  }
  check "performance_transactiongroup_count_check" {
    expr = "(count >= 0)"
  }
  check "performance_transactiongroup_error_count_check" {
    expr = "(error_count >= 0)"
  }
  unique "unique_transaction_project_op_method" {
    columns = [column.transaction, column.project_id, column.op, column.method, column.organization_id]
  }
  partition {
    type    = HASH
    columns = [column.organization_id]
  }
}
table "projects_issueeventprojecthourlystatistic" {
  schema = schema.public
  column "project_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.project_id, column.organization_id, column.date]
  }
  foreign_key "projects_issueeventprojecthourlystatistic_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "projects_issueeventprojecthourlystatistic_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "projects_issueeventprojecthourlystatistic_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "projects_logprojecthourlystatistic" {
  schema = schema.public
  column "project_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "level" {
    null = false
    type = smallint
  }
  column "service_bucket" {
    null    = false
    type    = smallint
    default = 0
  }
  column "environment_bucket" {
    null    = false
    type    = smallint
    default = 0
  }
  column "count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.project_id, column.organization_id, column.date, column.level, column.service_bucket, column.environment_bucket]
  }
  foreign_key "projects_logprojecthourlystatistic_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "projects_logprojecthourlystatistic_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "projects_logprojecthourlystatistic_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "projects_project" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "slug" {
    null = false
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "platform" {
    null = true
    type = character_varying(64)
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "first_event" {
    null = true
    type = timestamptz
  }
  column "scrub_ip_addresses" {
    null = false
    type = boolean
  }
  column "is_deleted" {
    null = false
    type = boolean
  }
  column "event_throttle_rate" {
    null = false
    type = smallint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_project_organization_id_c93e5ca2_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "projects_project_created_857f80bc" {
    columns = [column.created]
  }
  index "projects_project_organization_id_c93e5ca2" {
    columns = [column.organization_id]
  }
  index "projects_project_slug_2d50067a" {
    columns = [column.slug]
  }
  index "projects_project_slug_2d50067a_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "projects_project_event_throttle_rate_check" {
    expr = "(event_throttle_rate >= 0)"
  }
  unique "projects_project_organization_id_slug_ccb1507a_uniq" {
    columns = [column.organization_id, column.slug]
  }
}
table "projects_projectcounter" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "value" {
    null = false
    type = integer
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_projectcoun_project_id_c04e0a63_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  check "projects_projectcounter_value_check" {
    expr = "(value >= 0)"
  }
  unique "projects_projectcounter_project_id_key" {
    columns = [column.project_id]
  }
}
table "projects_projectkey" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "public_key" {
    null = false
    type = uuid
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "rate_limit_count" {
    null = true
    type = smallint
  }
  column "rate_limit_window" {
    null = true
    type = smallint
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "is_active" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_projectkey_project_id_4643220b_fk_projects_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "projects_projectkey_created_205a4393" {
    columns = [column.created]
  }
  index "projects_projectkey_project_id_4643220b" {
    columns = [column.project_id]
  }
  check "projects_projectkey_rate_limit_count_check" {
    expr = "(rate_limit_count >= 0)"
  }
  check "projects_projectkey_rate_limit_window_check" {
    expr = "(rate_limit_window >= 0)"
  }
  unique "projects_projectkey_public_key_key" {
    columns = [column.public_key]
  }
}
table "projects_transactioneventprojecthourlystatistic" {
  schema = schema.public
  column "project_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "count" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.project_id, column.organization_id, column.date]
  }
  foreign_key "projects_transactioneventprojecthourlystatistic_organization_id" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "projects_transactioneventprojecthourlystatistic_project_id_fkey" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "projects_transactioneventprojecthourlystatistic_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "projects_userprojectalert" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "status" {
    null = false
    type = smallint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_userproject_project_id_c739ba9c_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "projects_userprojectalert_user_id_80d9531e_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "projects_userprojectalert_project_id_c739ba9c" {
    columns = [column.project_id]
  }
  index "projects_userprojectalert_user_id_80d9531e" {
    columns = [column.user_id]
  }
  check "projects_userprojectalert_status_check" {
    expr = "(status >= 0)"
  }
  unique "projects_userprojectalert_user_id_project_id_3e086e1a_uniq" {
    columns = [column.user_id, column.project_id]
  }
}
table "releases_deploy" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "environment" {
    null = false
    type = character_varying(64)
  }
  column "url" {
    null = false
    type = character_varying(200)
  }
  column "date_started" {
    null = true
    type = timestamptz
  }
  column "date_finished" {
    null = true
    type = timestamptz
  }
  column "release_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "releases_deploy_release_id_3a597b34_fk_releases_release_id" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "releases_deploy_created_829d6082" {
    columns = [column.created]
  }
  index "releases_deploy_release_id_3a597b34" {
    columns = [column.release_id]
  }
}
table "releases_release" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  column "ref" {
    null = true
    type = character_varying(255)
  }
  column "url" {
    null = true
    type = character_varying(200)
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "released" {
    null = true
    type = timestamptz
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "commit_count" {
    null = false
    type = smallint
  }
  column "deploy_count" {
    null = false
    type = smallint
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "repository_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "releases_release_organization_id_d23b0b80_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "releases_release_owner_id_0dd1b0e8_fk_users_user_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "releases_release_repository_id_43e5ebf1_fk_sourcecod" {
    columns     = [column.repository_id]
    ref_columns = [table.sourcecode_repository.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "releases_release_created_e98aff08" {
    columns = [column.created]
  }
  index "releases_release_organization_id_d23b0b80" {
    columns = [column.organization_id]
  }
  index "releases_release_owner_id_0dd1b0e8" {
    columns = [column.owner_id]
  }
  index "releases_release_repository_id_43e5ebf1" {
    columns = [column.repository_id]
  }
  check "releases_release_commit_count_check" {
    expr = "(commit_count >= 0)"
  }
  check "releases_release_deploy_count_check" {
    expr = "(deploy_count >= 0)"
  }
  unique "releases_release_organization_id_version_3bc93805_uniq" {
    columns = [column.organization_id, column.version]
  }
}
table "releases_release_projects" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "release_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "releases_release_pro_project_id_375a83f0_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "releases_release_pro_release_id_7053dee2_fk_releases_" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "releases_release_projects_release_id_7053dee2_fk" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "releases_release_projects_project_id_375a83f0" {
    columns = [column.project_id]
  }
  index "releases_release_projects_release_id_7053dee2" {
    columns = [column.release_id]
  }
  unique "releases_release_projects_release_id_project_id_97bf4138_uniq" {
    columns = [column.release_id, column.project_id]
  }
}
table "releases_releaseproject" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "project_id" {
    null = false
    type = bigint
  }
  column "release_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "releases_releaseproj_project_id_69d8217c_fk_projects_" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "releases_releaseproj_release_id_962ac218_fk_releases_" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "releases_releaseproject_project_id_69d8217c" {
    columns = [column.project_id]
  }
  index "releases_releaseproject_release_id_962ac218" {
    columns = [column.release_id]
  }
  unique "releases_releaseproject_project_id_release_id_bca7fb5b_uniq" {
    columns = [column.project_id, column.release_id]
  }
}
table "socialaccount_socialaccount" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "provider" {
    null = false
    type = character_varying(200)
  }
  column "uid" {
    null = false
    type = character_varying(191)
  }
  column "last_login" {
    null = false
    type = timestamptz
  }
  column "date_joined" {
    null = false
    type = timestamptz
  }
  column "extra_data" {
    null = false
    type = jsonb
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "socialaccount_socialaccount_user_id_8146e70c_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "socialaccount_socialaccount_user_id_8146e70c" {
    columns = [column.user_id]
  }
  unique "socialaccount_socialaccount_provider_uid_fc810c6e_uniq" {
    columns = [column.provider, column.uid]
  }
}
table "socialaccount_socialapp" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "provider" {
    null = false
    type = character_varying(30)
  }
  column "name" {
    null = false
    type = character_varying(40)
  }
  column "client_id" {
    null = false
    type = character_varying(191)
  }
  column "secret" {
    null = false
    type = character_varying(191)
  }
  column "key" {
    null = false
    type = character_varying(191)
  }
  column "provider_id" {
    null = false
    type = character_varying(200)
  }
  column "settings" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
}
table "socialaccount_socialtoken" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "token" {
    null = false
    type = text
  }
  column "token_secret" {
    null = false
    type = text
  }
  column "expires_at" {
    null = true
    type = timestamptz
  }
  column "account_id" {
    null = false
    type = integer
  }
  column "app_id" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "socialaccount_social_account_id_951f210e_fk_socialacc" {
    columns     = [column.account_id]
    ref_columns = [table.socialaccount_socialaccount.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "socialaccount_social_app_id_636a42d7_fk_socialacc" {
    columns     = [column.app_id]
    ref_columns = [table.socialaccount_socialapp.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "socialaccount_socialtoken_account_id_951f210e" {
    columns = [column.account_id]
  }
  index "socialaccount_socialtoken_app_id_636a42d7" {
    columns = [column.app_id]
  }
  unique "socialaccount_socialtoken_app_id_account_id_fca4e0ac_uniq" {
    columns = [column.app_id, column.account_id]
  }
}
table "sourcecode_debugsymbolbundle" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "debug_id" {
    null = true
    type = uuid
  }
  column "last_used" {
    null = false
    type = timestamptz
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "release_id" {
    null = true
    type = bigint
  }
  column "sourcemap_file_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "sourcecode_debugsymb_organization_id_c377ccac_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sourcecode_debugsymb_release_id_79c3c867_fk_releases_" {
    columns     = [column.release_id]
    ref_columns = [table.releases_release.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sourcecode_debugsymb_sourcemap_file_id_4e691bcc_fk_files_fil" {
    columns     = [column.sourcemap_file_id]
    ref_columns = [table.files_file.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "sourcecode_debugsymbolbundle_file_id_ee9efbb7_fk_files_file_id" {
    columns     = [column.file_id]
    ref_columns = [table.files_file.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "sourcecode_debugsymbolbundle_created_04b3be0a" {
    columns = [column.created]
  }
  index "sourcecode_debugsymbolbundle_file_id_ee9efbb7" {
    columns = [column.file_id]
  }
  index "sourcecode_debugsymbolbundle_last_used_06b4437e" {
    columns = [column.last_used]
  }
  index "sourcecode_debugsymbolbundle_organization_id_c377ccac" {
    columns = [column.organization_id]
  }
  index "sourcecode_debugsymbolbundle_release_id_79c3c867" {
    columns = [column.release_id]
  }
  index "sourcecode_debugsymbolbundle_sourcemap_file_id_4e691bcc" {
    columns = [column.sourcemap_file_id]
  }
  check "debug_id_or_release_required" {
    expr = "((debug_id IS NOT NULL) OR (release_id IS NOT NULL))"
  }
  unique "unique_org_debug_id" {
    columns = [column.organization_id, column.debug_id]
  }
  unique "unique_release_file" {
    columns = [column.release_id, column.file_id]
  }
}
table "sourcecode_repository" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "url" {
    null = false
    type = character_varying(200)
  }
  column "provider" {
    null = false
    type = jsonb
  }
  column "status" {
    null = false
    type = character_varying(24)
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "sourcecode_repositor_organization_id_6d0fdfff_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "sourcecode_repository_created_88f70fc1" {
    columns = [column.created]
  }
  index "sourcecode_repository_organization_id_6d0fdfff" {
    columns = [column.organization_id]
  }
  unique "sourcecode_repository_unique_org_name" {
    columns = [column.organization_id, column.name]
  }
}
table "stripe_stripeprice" {
  schema = schema.public
  column "stripe_id" {
    null = false
    type = character_varying(30)
  }
  column "price" {
    null = false
    type = numeric(10,2)
  }
  column "nickname" {
    null = false
    type = character_varying(255)
  }
  column "product_id" {
    null = false
    type = character_varying(30)
  }
  column "interval" {
    null = false
    type = character_varying(20)
  }
  column "no_throttle" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.stripe_id]
  }
  foreign_key "stripe_stripeprice_product_id_ee929e62_fk_stripe_st" {
    columns     = [column.product_id]
    ref_columns = [table.stripe_stripeproduct.column.stripe_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "stripe_stripeprice_product_id_ee929e62" {
    columns = [column.product_id]
  }
  index "stripe_stripeprice_product_id_ee929e62_like" {
    on {
      column = column.product_id
      ops    = varchar_pattern_ops
    }
  }
  index "stripe_stripeprice_stripe_id_7ea89a65_like" {
    on {
      column = column.stripe_id
      ops    = varchar_pattern_ops
    }
  }
}
table "stripe_stripeproduct" {
  schema = schema.public
  column "stripe_id" {
    null = false
    type = character_varying(30)
  }
  column "description" {
    null = false
    type = text
  }
  column "events" {
    null = false
    type = bigint
  }
  column "is_public" {
    null = false
    type = boolean
  }
  column "name" {
    null = false
    type = character_varying
  }
  column "default_price_id" {
    null = true
    type = character_varying(30)
  }
  primary_key {
    columns = [column.stripe_id]
  }
  foreign_key "stripe_stripeproduct_default_price_id_dc02235b_fk_stripe_st" {
    columns     = [column.default_price_id]
    ref_columns = [table.stripe_stripeprice.column.stripe_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "stripe_stripeproduct_default_price_id_dc02235b" {
    columns = [column.default_price_id]
  }
  index "stripe_stripeproduct_default_price_id_dc02235b_like" {
    on {
      column = column.default_price_id
      ops    = varchar_pattern_ops
    }
  }
  index "stripe_stripeproduct_stripe_id_a4089bff_like" {
    on {
      column = column.stripe_id
      ops    = varchar_pattern_ops
    }
  }
  check "stripe_stripeproduct_events_check" {
    expr = "(events >= 0)"
  }
}
table "stripe_stripesubscription" {
  schema = schema.public
  column "stripe_id" {
    null = false
    type = character_varying(30)
  }
  column "current_period_start" {
    null = false
    type = timestamptz
  }
  column "current_period_end" {
    null = false
    type = timestamptz
  }
  column "organization_id" {
    null = true
    type = integer
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "price_id" {
    null = false
    type = character_varying(30)
  }
  column "collection_method" {
    null = false
    type = character_varying(20)
  }
  column "start_date" {
    null = false
    type = timestamptz
  }
  column "status" {
    null = false
    type = character_varying(18)
  }
  column "subscription_cycle_end" {
    null = true
    type = timestamptz
  }
  column "subscription_cycle_start" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.stripe_id]
  }
  foreign_key "stripe_stripesubscri_price_id_dea06771_fk_stripe_st" {
    columns     = [column.price_id]
    ref_columns = [table.stripe_stripeprice.column.stripe_id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "stripe_stripesubscription_organization_id_ea9b4d74_fk" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "stripe_stripesubscription_organization_id_ea9b4d74" {
    columns = [column.organization_id]
  }
  index "stripe_stripesubscription_price_id_dea06771" {
    columns = [column.price_id]
  }
  index "stripe_stripesubscription_price_id_dea06771_like" {
    on {
      column = column.price_id
      ops    = varchar_pattern_ops
    }
  }
  index "stripe_stripesubscription_status_311312b1" {
    columns = [column.status]
  }
  index "stripe_stripesubscription_status_311312b1_like" {
    on {
      column = column.status
      ops    = varchar_pattern_ops
    }
  }
  index "stripe_stripesubscription_stripe_id_375c22ac_like" {
    on {
      column = column.stripe_id
      ops    = varchar_pattern_ops
    }
  }
}
table "teams_team" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "slug" {
    null = false
    type = character_varying(50)
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "teams_team_organization_id_e98fce1d_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "teams_team_created_db346297" {
    columns = [column.created]
  }
  index "teams_team_organization_id_e98fce1d" {
    columns = [column.organization_id]
  }
  index "teams_team_slug_301a24e5" {
    columns = [column.slug]
  }
  index "teams_team_slug_301a24e5_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "teams_team_slug_organization_id_878caab4_uniq" {
    columns = [column.slug, column.organization_id]
  }
}
table "teams_team_members" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "team_id" {
    null = false
    type = bigint
  }
  column "organizationuser_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "teams_team_members_organizationuser_id_293156dc_fk_organizat" {
    columns     = [column.organizationuser_id]
    ref_columns = [table.organizations_ext_organizationuser.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "teams_team_members_team_id_ebb2d47d_fk_teams_team_id" {
    columns     = [column.team_id]
    ref_columns = [table.teams_team.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "teams_team_members_organizationuser_id_293156dc" {
    columns = [column.organizationuser_id]
  }
  index "teams_team_members_team_id_ebb2d47d" {
    columns = [column.team_id]
  }
  unique "teams_team_members_team_id_organizationuser_id_7aa377c7_uniq" {
    columns = [column.team_id, column.organizationuser_id]
  }
}
table "teams_team_projects" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "team_id" {
    null = false
    type = bigint
  }
  column "project_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "teams_team_projects_project_id_66bc9dde_fk_projects_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "teams_team_projects_team_id_ec11abec_fk_teams_team_id" {
    columns     = [column.team_id]
    ref_columns = [table.teams_team.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "teams_team_projects_project_id_66bc9dde" {
    columns = [column.project_id]
  }
  index "teams_team_projects_team_id_ec11abec" {
    columns = [column.team_id]
  }
  unique "teams_team_projects_team_id_project_id_eaad43ab_uniq" {
    columns = [column.team_id, column.project_id]
  }
}
table "uptime_monitor" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "monitor_type" {
    null = false
    type = character_varying(12)
  }
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "url" {
    null = false
    type = character_varying(2000)
  }
  column "expected_status" {
    null = true
    type = smallint
  }
  column "expected_body" {
    null = false
    type = character_varying(2000)
  }
  column "environment_id" {
    null = true
    type = bigint
  }
  column "organization_id" {
    null = false
    type = integer
  }
  column "project_id" {
    null = true
    type = bigint
  }
  column "endpoint_id" {
    null = true
    type = uuid
  }
  column "timeout" {
    null = true
    type = smallint
  }
  column "interval" {
    null = false
    type = smallint
  }
  column "cached_is_up" {
    null = true
    type = boolean
  }
  column "cached_last_change" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "uptime_monitor_environment_id_c1ee6182_fk_environme" {
    columns     = [column.environment_id]
    ref_columns = [table.environments_environment.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "uptime_monitor_organization_id_a3fa8f6e_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "uptime_monitor_project_id_99a888b1_fk_projects_project_id" {
    columns     = [column.project_id]
    ref_columns = [table.projects_project.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "uptime_moni_created_c41912_idx" {
    on {
      desc   = true
      column = column.created
    }
  }
  index "uptime_monitor_environment_id_c1ee6182" {
    columns = [column.environment_id]
  }
  index "uptime_monitor_organization_id_a3fa8f6e" {
    columns = [column.organization_id]
  }
  index "uptime_monitor_project_id_99a888b1" {
    columns = [column.project_id]
  }
  check "uptime_monitor_expected_status_check" {
    expr = "(expected_status >= 0)"
  }
  check "uptime_monitor_interval_check" {
    expr = "(\"interval\" >= 0)"
  }
  check "uptime_monitor_timeout_check" {
    expr = "(timeout >= 0)"
  }
}
table "uptime_monitorcheck" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v7()")
  }
  column "organization_id" {
    null = false
    type = bigint
  }
  column "monitor_id" {
    null = false
    type = bigint
  }
  column "start_check" {
    null = false
    type = timestamptz
  }
  column "response_time" {
    null = true
    type = integer
  }
  column "reason" {
    null = true
    type = smallint
  }
  column "is_up" {
    null = false
    type = boolean
  }
  column "is_change" {
    null = false
    type = boolean
  }
  column "data" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id, column.organization_id]
  }
  foreign_key "uptime_monitorcheck_monitor_id_fkey" {
    columns     = [column.monitor_id]
    ref_columns = [table.uptime_monitor.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "uptime_monitorcheck_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "uptime_moni_monitor_a89b32_idx" {
    on {
      column = column.monitor_id
    }
    on {
      desc   = true
      column = column.start_check
    }
  }
  index "uptime_moni_monitor_b6d442_idx" {
    on {
      column = column.monitor_id
    }
    on {
      column = column.is_change
    }
    on {
      desc   = true
      column = column.start_check
    }
  }
  partition {
    type    = RANGE
    columns = [column.id]
  }
}
table "uptime_statuspage" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "slug" {
    null = false
    type = character_varying(200)
  }
  column "is_public" {
    null = false
    type = boolean
  }
  column "organization_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "uptime_statuspage_organization_id_04168e62_fk_organizat" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "uptime_statuspage_created_dcaffaa9" {
    columns = [column.created]
  }
  index "uptime_statuspage_organization_id_04168e62" {
    columns = [column.organization_id]
  }
  index "uptime_statuspage_slug_b038369f" {
    columns = [column.slug]
  }
  index "uptime_statuspage_slug_b038369f_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "unique_organization_slug" {
    columns = [column.organization_id, column.slug]
  }
}
table "uptime_statuspage_monitors" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "statuspage_id" {
    null = false
    type = bigint
  }
  column "monitor_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "uptime_statuspage_mo_monitor_id_0fd95ae2_fk_uptime_mo" {
    columns     = [column.monitor_id]
    ref_columns = [table.uptime_monitor.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "uptime_statuspage_mo_statuspage_id_0336ae1f_fk_uptime_st" {
    columns     = [column.statuspage_id]
    ref_columns = [table.uptime_statuspage.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "uptime_statuspage_monitors_monitor_id_0fd95ae2" {
    columns = [column.monitor_id]
  }
  index "uptime_statuspage_monitors_statuspage_id_0336ae1f" {
    columns = [column.statuspage_id]
  }
  unique "uptime_statuspage_monito_statuspage_id_monitor_id_94a09566_uniq" {
    columns = [column.statuspage_id, column.monitor_id]
  }
}
table "uptime_uptimecheckhourlystatistic" {
  schema = schema.public
  column "organization_id" {
    null = false
    type = integer
  }
  column "date" {
    null = false
    type = timestamptz
  }
  column "count" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.organization_id, column.date]
  }
  foreign_key "uptime_uptimecheckhourlystatistic_organization_id_fkey" {
    columns     = [column.organization_id]
    ref_columns = [table.organizations_ext_organization.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  check "uptime_uptimecheckhourlystatistic_count_check" {
    expr = "(count >= 0)"
  }
  partition {
    type    = RANGE
    columns = [column.date]
  }
}
table "users_user" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "password" {
    null = false
    type = character_varying(128)
  }
  column "last_login" {
    null = true
    type = timestamptz
  }
  column "is_superuser" {
    null = false
    type = boolean
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "is_staff" {
    null = false
    type = boolean
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "subscribe_by_default" {
    null = false
    type = boolean
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "analytics" {
    null = true
    type = jsonb
  }
  column "options" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  unique "users_user_email_243f6e77_uniq" {
    columns = [column.email]
  }
}
table "users_user_groups" {
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
    type = bigint
  }
  column "group_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_user_groups_group_id_9afc8d0e_fk_auth_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.auth_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_user_groups_user_id_5f6f5a90_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_user_groups_group_id_9afc8d0e" {
    columns = [column.group_id]
  }
  index "users_user_groups_user_id_5f6f5a90" {
    columns = [column.user_id]
  }
  unique "users_user_groups_user_id_group_id_b88eab82_uniq" {
    columns = [column.user_id, column.group_id]
  }
}
table "users_user_user_permissions" {
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
    type = bigint
  }
  column "permission_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_user_user_perm_permission_id_0b93982e_fk_auth_perm" {
    columns     = [column.permission_id]
    ref_columns = [table.auth_permission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_user_user_permissions_user_id_20aca447_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_user_user_permissions_permission_id_0b93982e" {
    columns = [column.permission_id]
  }
  index "users_user_user_permissions_user_id_20aca447" {
    columns = [column.user_id]
  }
  unique "users_user_user_permissions_user_id_permission_id_43338c45_uniq" {
    columns = [column.user_id, column.permission_id]
  }
}
schema "public" {
  comment = "standard public schema"
}
