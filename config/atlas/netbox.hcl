Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

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
table "circuits_circuit" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "cid" {
    null = false
    type = character_varying(100)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "install_date" {
    null = true
    type = date
  }
  column "commit_rate" {
    null = true
    type = integer
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "provider_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "termination_a_id" {
    null = true
    type = bigint
  }
  column "termination_z_id" {
    null = true
    type = bigint
  }
  column "type_id" {
    null = false
    type = bigint
  }
  column "termination_date" {
    null = true
    type = date
  }
  column "provider_account_id" {
    null = true
    type = bigint
  }
  column "_abs_distance" {
    null = true
    type = numeric(13,4)
  }
  column "distance" {
    null = true
    type = numeric(8,2)
  }
  column "distance_unit" {
    null = true
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_circuit_owner_id_c330c2d0_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_provider_account_id_a7c8f61b_fk_circuits_" {
    columns     = [column.provider_account_id]
    ref_columns = [table.circuits_provideraccount.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_provider_id_d9195418_fk_circuits_provider_id" {
    columns     = [column.provider_id]
    ref_columns = [table.circuits_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_tenant_id_812508a5_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_termination_a_id_f891adac_fk_circuits_" {
    columns     = [column.termination_a_id]
    ref_columns = [table.circuits_circuittermination.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_termination_z_id_377b8551_fk_circuits_" {
    columns     = [column.termination_z_id]
    ref_columns = [table.circuits_circuittermination.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuit_type_id_1b9f485a_fk_circuits_circuittype_id" {
    columns     = [column.type_id]
    ref_columns = [table.circuits_circuittype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_circuit_owner_id_c330c2d0" {
    columns = [column.owner_id]
  }
  index "circuits_circuit_provider_account_id_a7c8f61b" {
    columns = [column.provider_account_id]
  }
  index "circuits_circuit_provider_id_d9195418" {
    columns = [column.provider_id]
  }
  index "circuits_circuit_tenant_id_812508a5" {
    columns = [column.tenant_id]
  }
  index "circuits_circuit_termination_a_id_f891adac" {
    columns = [column.termination_a_id]
  }
  index "circuits_circuit_termination_z_id_377b8551" {
    columns = [column.termination_z_id]
  }
  index "circuits_circuit_type_id_1b9f485a" {
    columns = [column.type_id]
  }
  check "circuits_circuit_commit_rate_check" {
    expr = "(commit_rate >= 0)"
  }
  unique "circuits_circuit_unique_provider_cid" {
    columns = [column.provider_id, column.cid]
  }
  unique "circuits_circuit_unique_provideraccount_cid" {
    columns = [column.provider_account_id, column.cid]
  }
}
table "circuits_circuitgroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_circuitgroup_owner_id_1edf4d64_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitgroup_tenant_id_5bafdc3f_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_circuitgroup_name_ec8ac1e5_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "circuits_circuitgroup_owner_id_1edf4d64" {
    columns = [column.owner_id]
  }
  index "circuits_circuitgroup_slug_61ca866b_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "circuits_circuitgroup_tenant_id_5bafdc3f" {
    columns = [column.tenant_id]
  }
  unique "circuits_circuitgroup_name_key" {
    columns = [column.name]
  }
  unique "circuits_circuitgroup_slug_key" {
    columns = [column.slug]
  }
}
table "circuits_circuitgroupassignment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "priority" {
    null = true
    type = character_varying(50)
  }
  column "member_id" {
    null = false
    type = bigint
  }
  column "group_id" {
    null = false
    type = bigint
  }
  column "member_type_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_circuitgrou_group_id_1a7b6580_fk_circuits_" {
    columns     = [column.group_id]
    ref_columns = [table.circuits_circuitgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitgrou_member_type_id_779d1a13_fk_django_co" {
    columns     = [column.member_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_circuitgroupassignment_group_id_1a7b6580" {
    columns = [column.group_id]
  }
  index "circuits_circuitgroupassignment_member_type_id_779d1a13" {
    columns = [column.member_type_id]
  }
  check "circuits_circuitgroupassignment_member_id_0c42fe52_check" {
    expr = "(member_id >= 0)"
  }
  unique "circuits_circuitgroupassignment_unique_member_group" {
    columns = [column.member_type_id, column.member_id, column.group_id]
  }
}
table "circuits_circuittermination" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "term_side" {
    null = false
    type = character_varying(1)
  }
  column "port_speed" {
    null = true
    type = integer
  }
  column "upstream_speed" {
    null = true
    type = integer
  }
  column "xconnect_id" {
    null = false
    type = character_varying(50)
  }
  column "pp_info" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "circuit_id" {
    null = false
    type = bigint
  }
  column "_provider_network_id" {
    null = true
    type = bigint
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "termination_id" {
    null = true
    type = bigint
  }
  column "termination_type_id" {
    null = true
    type = integer
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_region_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "_site_group_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_circuitterm__location_id_4a578dca_fk_dcim_loca" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitterm__provider_network_id_85ca661e_fk_circuits_" {
    columns     = [column._provider_network_id]
    ref_columns = [table.circuits_providernetwork.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitterm__region_id_1fa03379_fk_dcim_regi" {
    columns     = [column._region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitterm__site_group_id_ec0c1998_fk_dcim_site" {
    columns     = [column._site_group_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitterm_circuit_id_257e87e7_fk_circuits_" {
    columns     = [column.circuit_id]
    ref_columns = [table.circuits_circuit.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuitterm_termination_type_id_c9262c91_fk_django_co" {
    columns     = [column.termination_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuittermination__site_id_84942491_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_circuittermination_cable_id_35e9f703_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_ci_termina_505dda_idx" {
    columns = [column.termination_type_id, column.termination_id]
  }
  index "circuits_circuittermination__location_id_4a578dca" {
    columns = [column._location_id]
  }
  index "circuits_circuittermination__region_id_1fa03379" {
    columns = [column._region_id]
  }
  index "circuits_circuittermination__site_group_id_ec0c1998" {
    columns = [column._site_group_id]
  }
  index "circuits_circuittermination__site_id_84942491" {
    columns = [column._site_id]
  }
  index "circuits_circuittermination_cable_id_35e9f703" {
    columns = [column.cable_id]
  }
  index "circuits_circuittermination_circuit_id_257e87e7" {
    columns = [column.circuit_id]
  }
  index "circuits_circuittermination_provider_network_id_b0c660f1" {
    columns = [column._provider_network_id]
  }
  index "circuits_circuittermination_termination_type_id_c9262c91" {
    columns = [column.termination_type_id]
  }
  check "circuits_circuittermination_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "circuits_circuittermination_port_speed_check" {
    expr = "(port_speed >= 0)"
  }
  check "circuits_circuittermination_termination_id_check" {
    expr = "(termination_id >= 0)"
  }
  check "circuits_circuittermination_upstream_speed_check" {
    expr = "(upstream_speed >= 0)"
  }
  unique "circuits_circuittermination_unique_circuit_term_side" {
    columns = [column.circuit_id, column.term_side]
  }
}
table "circuits_circuittype" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_circuittype_owner_id_9c3200c2_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_circuittype_name_8256ea9a_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "circuits_circuittype_owner_id_9c3200c2" {
    columns = [column.owner_id]
  }
  index "circuits_circuittype_slug_9b4b3cf9_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "circuits_circuittype_name_key" {
    columns = [column.name]
  }
  unique "circuits_circuittype_slug_key" {
    columns = [column.slug]
  }
}
table "circuits_provider" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "comments" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_provider_owner_id_9f9749b4_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_provider_name_8f2514f5_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "circuits_provider_owner_id_9f9749b4" {
    columns = [column.owner_id]
  }
  index "circuits_provider_slug_c3c0aa10_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "circuits_provider_name_key" {
    columns = [column.name]
  }
  unique "circuits_provider_slug_key" {
    columns = [column.slug]
  }
}
table "circuits_provider_asns" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "provider_id" {
    null = false
    type = bigint
  }
  column "asn_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_provider_as_provider_id_becc3f7e_fk_circuits_" {
    columns     = [column.provider_id]
    ref_columns = [table.circuits_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_provider_asns_asn_id_0a6c53b3_fk_ipam_asn_id" {
    columns     = [column.asn_id]
    ref_columns = [table.ipam_asn.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_provider_asns_asn_id_0a6c53b3" {
    columns = [column.asn_id]
  }
  index "circuits_provider_asns_provider_id_becc3f7e" {
    columns = [column.provider_id]
  }
  unique "circuits_provider_asns_provider_id_asn_id_6e573798_uniq" {
    columns = [column.provider_id, column.asn_id]
  }
}
table "circuits_provideraccount" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "account" {
    null = false
    type = character_varying(100)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "provider_id" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_provideracc_provider_id_4bcd7e50_fk_circuits_" {
    columns     = [column.provider_id]
    ref_columns = [table.circuits_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_provideraccount_owner_id_6dcd4819_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_provideraccount_owner_id_6dcd4819" {
    columns = [column.owner_id]
  }
  index "circuits_provideraccount_provider_id_4bcd7e50" {
    columns = [column.provider_id]
  }
  index "circuits_provideraccount_unique_provider_name" {
    unique  = true
    columns = [column.provider_id, column.name]
    where   = "(NOT ((name)::text = ''::text))"
  }
  unique "circuits_provideraccount_unique_provider_account" {
    columns = [column.provider_id, column.account]
  }
}
table "circuits_providernetwork" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "provider_id" {
    null = false
    type = bigint
  }
  column "service_id" {
    null = false
    type = character_varying(100)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_providernet_provider_id_7992236c_fk_circuits_" {
    columns     = [column.provider_id]
    ref_columns = [table.circuits_provider.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_providernetwork_owner_id_caa8afde_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_providernetwork_owner_id_caa8afde" {
    columns = [column.owner_id]
  }
  index "circuits_providernetwork_provider_id_7992236c" {
    columns = [column.provider_id]
  }
  unique "circuits_providernetwork_unique_provider_name" {
    columns = [column.provider_id, column.name]
  }
}
table "circuits_virtualcircuit" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "cid" {
    null = false
    type = character_varying(100)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "provider_account_id" {
    null = true
    type = bigint
  }
  column "provider_network_id" {
    null = false
    type = bigint
  }
  column "type_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_virtualcirc_provider_account_id_d942f455_fk_circuits_" {
    columns     = [column.provider_account_id]
    ref_columns = [table.circuits_provideraccount.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_virtualcirc_provider_network_id_a902f409_fk_circuits_" {
    columns     = [column.provider_network_id]
    ref_columns = [table.circuits_providernetwork.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_virtualcirc_type_id_8527d682_fk_circuits_" {
    columns     = [column.type_id]
    ref_columns = [table.circuits_virtualcircuittype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_virtualcircuit_owner_id_89564a1e_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_virtualcircuit_tenant_id_4458eca7_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_virtualcircuit_owner_id_89564a1e" {
    columns = [column.owner_id]
  }
  index "circuits_virtualcircuit_provider_account_id_d942f455" {
    columns = [column.provider_account_id]
  }
  index "circuits_virtualcircuit_provider_network_id_a902f409" {
    columns = [column.provider_network_id]
  }
  index "circuits_virtualcircuit_tenant_id_4458eca7" {
    columns = [column.tenant_id]
  }
  index "circuits_virtualcircuit_type_id_8527d682" {
    columns = [column.type_id]
  }
  unique "circuits_virtualcircuit_unique_provider_network_cid" {
    columns = [column.provider_network_id, column.cid]
  }
  unique "circuits_virtualcircuit_unique_provideraccount_cid" {
    columns = [column.provider_account_id, column.cid]
  }
}
table "circuits_virtualcircuittermination" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "role" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "interface_id" {
    null = false
    type = bigint
  }
  column "virtual_circuit_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_virtualcirc_interface_id_d764b232_fk_dcim_inte" {
    columns     = [column.interface_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "circuits_virtualcirc_virtual_circuit_id_ca588886_fk_circuits_" {
    columns     = [column.virtual_circuit_id]
    ref_columns = [table.circuits_virtualcircuit.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_virtualcircuittermination_virtual_circuit_id_ca588886" {
    columns = [column.virtual_circuit_id]
  }
  unique "circuits_virtualcircuittermination_interface_id_key" {
    columns = [column.interface_id]
  }
}
table "circuits_virtualcircuittype" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "circuits_virtualcircuittype_owner_id_12a50b80_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "circuits_virtualcircuittype_name_5184db16_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "circuits_virtualcircuittype_owner_id_12a50b80" {
    columns = [column.owner_id]
  }
  index "circuits_virtualcircuittype_slug_75d5c661_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "circuits_virtualcircuittype_name_key" {
    columns = [column.name]
  }
  unique "circuits_virtualcircuittype_slug_key" {
    columns = [column.slug]
  }
}
table "core_autosyncrecord" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "datafile_id" {
    null = false
    type = bigint
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_autosyncrecord_datafile_id_f2aad29e_fk_core_datafile_id" {
    columns     = [column.datafile_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "core_autosyncrecord_object_type_id_62506cf6_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_autosyncrecord_datafile_id_f2aad29e" {
    columns = [column.datafile_id]
  }
  index "core_autosyncrecord_object_type_id_62506cf6" {
    columns = [column.object_type_id]
  }
  check "core_autosyncrecord_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "core_autosyncrecord_object" {
    columns = [column.object_type_id, column.object_id]
  }
}
table "core_configrevision" {
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
  column "comment" {
    null = false
    type = character_varying(200)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "active" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "unique_active_config_revision" {
    unique  = true
    columns = [column.active]
    where   = "active"
  }
}
table "core_datafile" {
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
  column "last_updated" {
    null = false
    type = timestamptz
  }
  column "path" {
    null = false
    type = character_varying(1000)
  }
  column "size" {
    null = false
    type = integer
  }
  column "hash" {
    null = false
    type = character_varying(64)
  }
  column "data" {
    null = false
    type = bytea
  }
  column "source_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_datafile_source_id_8d675be2_fk_core_datasource_id" {
    columns     = [column.source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_datafile_source_id_8d675be2" {
    columns = [column.source_id]
  }
  check "core_datafile_size_check" {
    expr = "(size >= 0)"
  }
  unique "core_datafile_unique_source_path" {
    columns = [column.source_id, column.path]
  }
}
table "core_datasource" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "source_url" {
    null = false
    type = character_varying(200)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "ignore_rules" {
    null = false
    type = text
  }
  column "parameters" {
    null = true
    type = jsonb
  }
  column "last_synced" {
    null = true
    type = timestamptz
  }
  column "sync_interval" {
    null = true
    type = smallint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_datasource_owner_id_3f4e6ba5_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_datasource_name_17788499_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "core_datasource_owner_id_3f4e6ba5" {
    columns = [column.owner_id]
  }
  check "core_datasource_sync_interval_check" {
    expr = "(sync_interval >= 0)"
  }
  unique "core_datasource_name_key" {
    columns = [column.name]
  }
}
table "core_job" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "object_id" {
    null = true
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "scheduled" {
    null = true
    type = timestamptz
  }
  column "interval" {
    null = true
    type = integer
  }
  column "started" {
    null = true
    type = timestamptz
  }
  column "completed" {
    null = true
    type = timestamptz
  }
  column "status" {
    null = false
    type = character_varying(30)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "job_id" {
    null = false
    type = uuid
  }
  column "object_type_id" {
    null = true
    type = integer
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "error" {
    null = false
    type = text
  }
  column "log_entries" {
    null = false
    type = sql("jsonb[]")
  }
  column "queue_name" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_job_object_type_id_ea17469a_fk_django_content_type_id" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "core_job_user_id_b69eefda_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_job_object__c664ac_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "core_job_object_type_id_ea17469a" {
    columns = [column.object_type_id]
  }
  index "core_job_user_id_b69eefda" {
    columns = [column.user_id]
  }
  check "core_job_interval_check" {
    expr = "(\"interval\" >= 0)"
  }
  check "core_job_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "core_job_job_id_key" {
    columns = [column.job_id]
  }
}
table "core_managedfile" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "data_path" {
    null = false
    type = character_varying(1000)
  }
  column "data_synced" {
    null = true
    type = timestamptz
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "file_root" {
    null = false
    type = character_varying(1000)
  }
  column "file_path" {
    null = false
    type = character_varying(100)
  }
  column "data_file_id" {
    null = true
    type = bigint
  }
  column "data_source_id" {
    null = true
    type = bigint
  }
  column "auto_sync_enabled" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_managedfile_data_file_id_2b6fc95e_fk_core_datafile_id" {
    columns     = [column.data_file_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "core_managedfile_data_source_id_647d5dbe_fk_core_datasource_id" {
    columns     = [column.data_source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_managedfile_data_file_id_2b6fc95e" {
    columns = [column.data_file_id]
  }
  index "core_managedfile_data_source_id_647d5dbe" {
    columns = [column.data_source_id]
  }
  unique "core_managedfile_unique_root_path" {
    columns = [column.file_root, column.file_path]
  }
}
table "core_objectchange" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "time" {
    null = false
    type = timestamptz
  }
  column "user_name" {
    null = false
    type = character_varying(150)
  }
  column "request_id" {
    null = false
    type = uuid
  }
  column "action" {
    null = false
    type = character_varying(50)
  }
  column "changed_object_id" {
    null = false
    type = bigint
  }
  column "related_object_id" {
    null = true
    type = bigint
  }
  column "object_repr" {
    null = false
    type = character_varying(200)
  }
  column "prechange_data" {
    null = true
    type = jsonb
  }
  column "postchange_data" {
    null = true
    type = jsonb
  }
  column "changed_object_type_id" {
    null = false
    type = integer
  }
  column "related_object_type_id" {
    null = true
    type = integer
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "message" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "core_objectchange_changed_object_type_id_2070ade6" {
    columns     = [column.changed_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "core_objectchange_related_object_type_id_b80958af" {
    columns     = [column.related_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "core_objectchange_user_id_2b2142be" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_objectchange_changed_object_type_id_2070ade6" {
    columns = [column.changed_object_type_id]
  }
  index "core_objectchange_changed_object_type_id_cha_79a9ed1e" {
    columns = [column.changed_object_type_id, column.changed_object_id]
  }
  index "core_objectchange_related_object_type_id_b80958af" {
    columns = [column.related_object_type_id]
  }
  index "core_objectchange_related_object_type_id_rel_a71d604a" {
    columns = [column.related_object_type_id, column.related_object_id]
  }
  index "core_objectchange_request_id_d9d160ac" {
    columns = [column.request_id]
  }
  index "core_objectchange_time_800f60a5" {
    columns = [column.time]
  }
  index "core_objectchange_user_id_2b2142be" {
    columns = [column.user_id]
  }
  check "core_objectchange_changed_object_id_check" {
    expr = "(changed_object_id >= 0)"
  }
  check "core_objectchange_related_object_id_check" {
    expr = "(related_object_id >= 0)"
  }
}
table "core_objecttype" {
  schema = schema.public
  column "contenttype_ptr_id" {
    null = false
    type = integer
  }
  column "public" {
    null = false
    type = boolean
  }
  column "features" {
    null = false
    type = sql("character varying(50)[]")
  }
  primary_key {
    columns = [column.contenttype_ptr_id]
  }
  foreign_key "core_objecttype_contenttype_ptr_id_d92548f5_fk_django_co" {
    columns     = [column.contenttype_ptr_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "core_object_feature_aec4de_gin" {
    columns = [column.features]
    type    = GIN
  }
}
table "dcim_cable" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "label" {
    null = false
    type = character_varying(100)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "length" {
    null = true
    type = numeric(8,2)
  }
  column "length_unit" {
    null = true
    type = character_varying(50)
  }
  column "_abs_length" {
    null = true
    type = numeric(10,4)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "profile" {
    null = false
    type = character_varying(50)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_cable_owner_id_9cea1430_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cable_tenant_id_3a7fdbb8_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_cable_owner_id_9cea1430" {
    columns = [column.owner_id]
  }
  index "dcim_cable_tenant_id_3a7fdbb8" {
    columns = [column.tenant_id]
  }
}
table "dcim_cablepath" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "_nodes" {
    null = false
    type = sql("character varying(40)[]")
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "is_split" {
    null = false
    type = boolean
  }
  column "path" {
    null = false
    type = jsonb
  }
  column "is_complete" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
}
table "dcim_cabletermination" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "cable_end" {
    null = false
    type = character_varying(1)
  }
  column "termination_id" {
    null = false
    type = bigint
  }
  column "cable_id" {
    null = false
    type = bigint
  }
  column "termination_type_id" {
    null = false
    type = integer
  }
  column "_device_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "connector" {
    null = true
    type = smallint
  }
  column "positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_cableterminatio_termination_type_id_20da439e_fk_django_co" {
    columns     = [column.termination_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cabletermination__device_id_f5884934_fk_dcim_device_id" {
    columns     = [column._device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cabletermination__location_id_ff4be503_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cabletermination__rack_id_83a548e1_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cabletermination__site_id_616962fa_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_cabletermination_cable_id_b50010d1_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_cabletermination__device_id_f5884934" {
    columns = [column._device_id]
  }
  index "dcim_cabletermination__location_id_ff4be503" {
    columns = [column._location_id]
  }
  index "dcim_cabletermination__rack_id_83a548e1" {
    columns = [column._rack_id]
  }
  index "dcim_cabletermination__site_id_616962fa" {
    columns = [column._site_id]
  }
  index "dcim_cabletermination_cable_id_b50010d1" {
    columns = [column.cable_id]
  }
  index "dcim_cabletermination_termination_type_id_20da439e" {
    columns = [column.termination_type_id]
  }
  check "dcim_cabletermination_connector_check" {
    expr = "(connector >= 0)"
  }
  check "dcim_cabletermination_termination_id_check" {
    expr = "(termination_id >= 0)"
  }
  unique "dcim_cabletermination_unique_connector" {
    columns = [column.cable_id, column.cable_end, column.connector]
  }
  unique "dcim_cabletermination_unique_termination" {
    columns = [column.termination_type_id, column.termination_id]
  }
}
table "dcim_consoleport" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "speed" {
    null = true
    type = integer
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_consoleport__location_id_d0e7437b_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport__path_id_e40a4436_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport__rack_id_71f16827_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport__site_id_9652df9c_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport_cable_id_a9ae5465_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport_device_id_f2d90d3c_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport_module_id_d17b2519_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleport_owner_id_0648eae1_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_consoleport__location_id_d0e7437b" {
    columns = [column._location_id]
  }
  index "dcim_consoleport__path_id_e40a4436" {
    columns = [column._path_id]
  }
  index "dcim_consoleport__rack_id_71f16827" {
    columns = [column._rack_id]
  }
  index "dcim_consoleport__site_id_9652df9c" {
    columns = [column._site_id]
  }
  index "dcim_consoleport_cable_id_a9ae5465" {
    columns = [column.cable_id]
  }
  index "dcim_consoleport_device_id_f2d90d3c" {
    columns = [column.device_id]
  }
  index "dcim_consoleport_module_id_d17b2519" {
    columns = [column.module_id]
  }
  index "dcim_consoleport_owner_id_0648eae1" {
    columns = [column.owner_id]
  }
  check "dcim_consoleport_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_consoleport_speed_check" {
    expr = "(speed >= 0)"
  }
  unique "dcim_consoleport_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_consoleporttemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_consoleporttemp_device_type_id_075d4015_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleporttemp_module_type_id_c0f35d97_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_consoleporttemplate_device_type_id_075d4015" {
    columns = [column.device_type_id]
  }
  index "dcim_consoleporttemplate_module_type_id_c0f35d97" {
    columns = [column.module_type_id]
  }
  unique "dcim_consoleporttemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_consoleporttemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_consoleserverport" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "speed" {
    null = true
    type = integer
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_consoleserverpo__location_id_7525ec0e_fk_dcim_loca" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport__path_id_dc5abe09_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport__rack_id_3eea9f1b_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport__site_id_c500ac62_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport_cable_id_f2940dfd_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport_device_id_d9866581_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport_module_id_d060cfc8_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverport_owner_id_12b1a827_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_consoleserverport__location_id_7525ec0e" {
    columns = [column._location_id]
  }
  index "dcim_consoleserverport__path_id_dc5abe09" {
    columns = [column._path_id]
  }
  index "dcim_consoleserverport__rack_id_3eea9f1b" {
    columns = [column._rack_id]
  }
  index "dcim_consoleserverport__site_id_c500ac62" {
    columns = [column._site_id]
  }
  index "dcim_consoleserverport_cable_id_f2940dfd" {
    columns = [column.cable_id]
  }
  index "dcim_consoleserverport_device_id_d9866581" {
    columns = [column.device_id]
  }
  index "dcim_consoleserverport_module_id_d060cfc8" {
    columns = [column.module_id]
  }
  index "dcim_consoleserverport_owner_id_12b1a827" {
    columns = [column.owner_id]
  }
  check "dcim_consoleserverport_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_consoleserverport_speed_check" {
    expr = "(speed >= 0)"
  }
  unique "dcim_consoleserverport_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_consoleserverporttemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_consoleserverpo_device_type_id_579bdc86_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_consoleserverpo_module_type_id_4abf751a_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_consoleserverporttemplate_device_type_id_579bdc86" {
    columns = [column.device_type_id]
  }
  index "dcim_consoleserverporttemplate_module_type_id_4abf751a" {
    columns = [column.module_type_id]
  }
  unique "dcim_consoleserverporttemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_consoleserverporttemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_device" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "local_context_data" {
    null = true
    type = jsonb
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "serial" {
    null = false
    type = character_varying(50)
  }
  column "asset_tag" {
    null = true
    type = character_varying(50)
  }
  column "position" {
    null = true
    type = numeric(4,1)
  }
  column "face" {
    null = true
    type = character_varying(50)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "vc_position" {
    null = true
    type = integer
  }
  column "vc_priority" {
    null = true
    type = smallint
  }
  column "comments" {
    null = false
    type = text
  }
  column "cluster_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = false
    type = bigint
  }
  column "device_type_id" {
    null = false
    type = bigint
  }
  column "location_id" {
    null = true
    type = bigint
  }
  column "platform_id" {
    null = true
    type = bigint
  }
  column "primary_ip4_id" {
    null = true
    type = bigint
  }
  column "primary_ip6_id" {
    null = true
    type = bigint
  }
  column "rack_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "virtual_chassis_id" {
    null = true
    type = bigint
  }
  column "airflow" {
    null = true
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "config_template_id" {
    null = true
    type = bigint
  }
  column "latitude" {
    null = true
    type = numeric(8,6)
  }
  column "longitude" {
    null = true
    type = numeric(9,6)
  }
  column "oob_ip_id" {
    null = true
    type = bigint
  }
  column "console_port_count" {
    null = false
    type = bigint
  }
  column "console_server_port_count" {
    null = false
    type = bigint
  }
  column "power_port_count" {
    null = false
    type = bigint
  }
  column "power_outlet_count" {
    null = false
    type = bigint
  }
  column "interface_count" {
    null = false
    type = bigint
  }
  column "front_port_count" {
    null = false
    type = bigint
  }
  column "rear_port_count" {
    null = false
    type = bigint
  }
  column "device_bay_count" {
    null = false
    type = bigint
  }
  column "module_bay_count" {
    null = false
    type = bigint
  }
  column "inventory_item_count" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_device_cluster_id_cf852f78_fk_virtualization_cluster_id" {
    columns     = [column.cluster_id]
    ref_columns = [table.virtualization_cluster.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_config_template_id_316328c4_fk_extras_co" {
    columns     = [column.config_template_id]
    ref_columns = [table.extras_configtemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_device_type_id_d61b4086_fk_dcim_devicetype_id" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_location_id_11a7bedb_fk_dcim_location_id" {
    columns     = [column.location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_oob_ip_id_5e7219c1_fk_ipam_ipaddress_id" {
    columns     = [column.oob_ip_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_owner_id_87378f76_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_platform_id_468138f1_fk_dcim_platform_id" {
    columns     = [column.platform_id]
    ref_columns = [table.dcim_platform.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_primary_ip4_id_2ccd943a_fk_ipam_ipaddress_id" {
    columns     = [column.primary_ip4_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_primary_ip6_id_d180fe91_fk_ipam_ipaddress_id" {
    columns     = [column.primary_ip6_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_rack_id_23bde71f_fk_dcim_rack_id" {
    columns     = [column.rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_role_id_61edcc33_fk_dcim_devicerole_id" {
    columns     = [column.role_id]
    ref_columns = [table.dcim_devicerole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_site_id_ff897cf6_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_tenant_id_dcea7969_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_device_virtual_chassis_id_aed51693_fk_dcim_virt" {
    columns     = [column.virtual_chassis_id]
    ref_columns = [table.dcim_virtualchassis.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_device_asset_tag_8dac1079_like" {
    on {
      column = column.asset_tag
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_device_cluster_id_cf852f78" {
    columns = [column.cluster_id]
  }
  index "dcim_device_config_template_id_316328c4" {
    columns = [column.config_template_id]
  }
  index "dcim_device_device_role_id_682e8188" {
    columns = [column.role_id]
  }
  index "dcim_device_device_type_id_d61b4086" {
    columns = [column.device_type_id]
  }
  index "dcim_device_location_id_11a7bedb" {
    columns = [column.location_id]
  }
  index "dcim_device_owner_id_87378f76" {
    columns = [column.owner_id]
  }
  index "dcim_device_platform_id_468138f1" {
    columns = [column.platform_id]
  }
  index "dcim_device_rack_id_23bde71f" {
    columns = [column.rack_id]
  }
  index "dcim_device_site_id_ff897cf6" {
    columns = [column.site_id]
  }
  index "dcim_device_tenant_id_dcea7969" {
    columns = [column.tenant_id]
  }
  index "dcim_device_unique_name_site" {
    unique = true
    where  = "(tenant_id IS NULL)"
    on {
      expr = "lower((name)::text)"
    }
    on {
      column = column.site_id
    }
  }
  index "dcim_device_unique_name_site_tenant" {
    unique = true
    on {
      expr = "lower((name)::text)"
    }
    on {
      column = column.site_id
    }
    on {
      column = column.tenant_id
    }
  }
  index "dcim_device_virtual_chassis_id_aed51693" {
    columns = [column.virtual_chassis_id]
  }
  check "dcim_device_vc_position_check" {
    expr = "(vc_position >= 0)"
  }
  check "dcim_device_vc_priority_check" {
    expr = "(vc_priority >= 0)"
  }
  unique "dcim_device_asset_tag_key" {
    columns = [column.asset_tag]
  }
  unique "dcim_device_oob_ip_id_key" {
    columns = [column.oob_ip_id]
  }
  unique "dcim_device_primary_ip4_id_key" {
    columns = [column.primary_ip4_id]
  }
  unique "dcim_device_primary_ip6_id_key" {
    columns = [column.primary_ip6_id]
  }
  unique "dcim_device_unique_rack_position_face" {
    columns = [column.rack_id, column.position, column.face]
  }
  unique "dcim_device_unique_virtual_chassis_vc_position" {
    columns = [column.virtual_chassis_id, column.vc_position]
  }
}
table "dcim_devicebay" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "installed_device_id" {
    null = true
    type = bigint
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_devicebay__location_id_6c869a87_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicebay__rack_id_75672431_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicebay__site_id_8ddc30f4_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicebay_device_id_0c8a1218_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicebay_installed_device_id_04618112_fk_dcim_device_id" {
    columns     = [column.installed_device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicebay_owner_id_d7bcb3e6_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_devicebay__location_id_6c869a87" {
    columns = [column._location_id]
  }
  index "dcim_devicebay__rack_id_75672431" {
    columns = [column._rack_id]
  }
  index "dcim_devicebay__site_id_8ddc30f4" {
    columns = [column._site_id]
  }
  index "dcim_devicebay_device_id_0c8a1218" {
    columns = [column.device_id]
  }
  index "dcim_devicebay_owner_id_d7bcb3e6" {
    columns = [column.owner_id]
  }
  unique "dcim_devicebay_installed_device_id_key" {
    columns = [column.installed_device_id]
  }
  unique "dcim_devicebay_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_devicebaytemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "device_type_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_devicebaytempla_device_type_id_f4b24a29_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_devicebaytemplate_device_type_id_f4b24a29" {
    columns = [column.device_type_id]
  }
  unique "dcim_devicebaytemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
}
table "dcim_devicerole" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "vm_role" {
    null = false
    type = boolean
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "config_template_id" {
    null = true
    type = bigint
  }
  column "level" {
    null = false
    type = integer
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_devicerole_config_template_id_5874002c_fk_extras_co" {
    columns     = [column.config_template_id]
    ref_columns = [table.extras_configtemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicerole_owner_id_fdcc527d_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicerole_parent_id_7f9ccf87_fk_dcim_devicerole_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_devicerole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_devicerole_config_template_id_5874002c" {
    columns = [column.config_template_id]
  }
  index "dcim_devicerole_name" {
    unique  = true
    columns = [column.name]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_devicerole_owner_id_fdcc527d" {
    columns = [column.owner_id]
  }
  index "dcim_devicerole_parent_id_7f9ccf87" {
    columns = [column.parent_id]
  }
  index "dcim_devicerole_slug" {
    unique  = true
    columns = [column.slug]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_devicerole_slug_7952643b" {
    columns = [column.slug]
  }
  index "dcim_devicerole_slug_7952643b_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_devicerole_tree_id_196b114c" {
    columns = [column.tree_id]
  }
  index "dcim_devicerole_tree_id_lfbf11" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_devicerole_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_devicerole_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_devicerole_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_devicerole_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_devicerole_parent_name" {
    columns = [column.parent_id, column.name]
  }
  unique "dcim_devicerole_parent_slug" {
    columns = [column.parent_id, column.slug]
  }
}
table "dcim_devicetype" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "model" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "part_number" {
    null = false
    type = character_varying(50)
  }
  column "u_height" {
    null = false
    type = numeric(4,1)
  }
  column "is_full_depth" {
    null = false
    type = boolean
  }
  column "subdevice_role" {
    null = true
    type = character_varying(50)
  }
  column "front_image" {
    null = false
    type = character_varying(100)
  }
  column "rear_image" {
    null = false
    type = character_varying(100)
  }
  column "comments" {
    null = false
    type = text
  }
  column "manufacturer_id" {
    null = false
    type = bigint
  }
  column "airflow" {
    null = true
    type = character_varying(50)
  }
  column "weight" {
    null = true
    type = numeric(8,2)
  }
  column "weight_unit" {
    null = true
    type = character_varying(50)
  }
  column "_abs_weight" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "default_platform_id" {
    null = true
    type = bigint
  }
  column "console_port_template_count" {
    null = false
    type = bigint
  }
  column "console_server_port_template_count" {
    null = false
    type = bigint
  }
  column "power_port_template_count" {
    null = false
    type = bigint
  }
  column "power_outlet_template_count" {
    null = false
    type = bigint
  }
  column "interface_template_count" {
    null = false
    type = bigint
  }
  column "front_port_template_count" {
    null = false
    type = bigint
  }
  column "rear_port_template_count" {
    null = false
    type = bigint
  }
  column "device_bay_template_count" {
    null = false
    type = bigint
  }
  column "module_bay_template_count" {
    null = false
    type = bigint
  }
  column "inventory_item_template_count" {
    null = false
    type = bigint
  }
  column "exclude_from_utilization" {
    null = false
    type = boolean
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "device_count" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_devicetype_default_platform_id_1f6ff6ac_fk_dcim_plat" {
    columns     = [column.default_platform_id]
    ref_columns = [table.dcim_platform.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicetype_manufacturer_id_a3e8029e_fk_dcim_manu" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_devicetype_owner_id_243048ed_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_devicetype_default_platform_id_1f6ff6ac" {
    columns = [column.default_platform_id]
  }
  index "dcim_devicetype_manufacturer_id_a3e8029e" {
    columns = [column.manufacturer_id]
  }
  index "dcim_devicetype_owner_id_243048ed" {
    columns = [column.owner_id]
  }
  index "dcim_devicetype_slug_448745bd" {
    columns = [column.slug]
  }
  index "dcim_devicetype_slug_448745bd_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "dcim_devicetype__abs_weight_check" {
    expr = "(_abs_weight >= 0)"
  }
  unique "dcim_devicetype_unique_manufacturer_model" {
    columns = [column.manufacturer_id, column.model]
  }
  unique "dcim_devicetype_unique_manufacturer_slug" {
    columns = [column.manufacturer_id, column.slug]
  }
}
table "dcim_frontport" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  column "positions" {
    null = false
    type = smallint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_frontport__location_id_dc0402e7_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport__rack_id_1ba6d11c_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport__site_id_51efdefe_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport_cable_id_04ff8aab_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport_device_id_950557b5_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport_module_id_952c3f9a_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontport_owner_id_dfb61151_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_frontport__location_id_dc0402e7" {
    columns = [column._location_id]
  }
  index "dcim_frontport__rack_id_1ba6d11c" {
    columns = [column._rack_id]
  }
  index "dcim_frontport__site_id_51efdefe" {
    columns = [column._site_id]
  }
  index "dcim_frontport_cable_id_04ff8aab" {
    columns = [column.cable_id]
  }
  index "dcim_frontport_device_id_950557b5" {
    columns = [column.device_id]
  }
  index "dcim_frontport_module_id_952c3f9a" {
    columns = [column.module_id]
  }
  index "dcim_frontport_owner_id_dfb61151" {
    columns = [column.owner_id]
  }
  check "dcim_frontport_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_frontport_positions_check" {
    expr = "(positions >= 0)"
  }
  unique "dcim_frontport_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_frontporttemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  column "positions" {
    null = false
    type = smallint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_frontporttempla_device_type_id_f088b952_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_frontporttempla_module_type_id_66851ff9_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_frontporttemplate_device_type_id_f088b952" {
    columns = [column.device_type_id]
  }
  index "dcim_frontporttemplate_module_type_id_66851ff9" {
    columns = [column.module_type_id]
  }
  check "dcim_frontporttemplate_positions_check" {
    expr = "(positions >= 0)"
  }
  unique "dcim_frontporttemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_frontporttemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_interface" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "mtu" {
    null = true
    type = integer
  }
  column "mode" {
    null = true
    type = character_varying(50)
  }
  column "_name" {
    null = false
    type = character_varying(100)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "mgmt_only" {
    null = false
    type = boolean
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "lag_id" {
    null = true
    type = bigint
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "untagged_vlan_id" {
    null = true
    type = bigint
  }
  column "wwn" {
    null = true
    type = macaddr8
  }
  column "bridge_id" {
    null = true
    type = bigint
  }
  column "rf_role" {
    null = true
    type = character_varying(30)
  }
  column "rf_channel" {
    null = true
    type = character_varying(50)
  }
  column "rf_channel_frequency" {
    null = true
    type = numeric(7,2)
  }
  column "rf_channel_width" {
    null = true
    type = numeric(7,3)
  }
  column "tx_power" {
    null = true
    type = smallint
  }
  column "wireless_link_id" {
    null = true
    type = bigint
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "vrf_id" {
    null = true
    type = bigint
  }
  column "duplex" {
    null = true
    type = character_varying(50)
  }
  column "speed" {
    null = true
    type = integer
  }
  column "poe_mode" {
    null = true
    type = character_varying(50)
  }
  column "poe_type" {
    null = true
    type = character_varying(50)
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "vlan_translation_policy_id" {
    null = true
    type = bigint
  }
  column "qinq_svlan_id" {
    null = true
    type = bigint
  }
  column "primary_mac_address_id" {
    null = true
    type = bigint
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_interface__location_id_72d5e107_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface__path_id_f8f4f7f0_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface__rack_id_0d3f84a6_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface__site_id_0fffd4ef_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_bridge_id_f2a8df85_fk_dcim_interface_id" {
    columns     = [column.bridge_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_cable_id_1b264edb_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_device_id_359c6115_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_lag_id_ea1a1d12_fk_dcim_interface_id" {
    columns     = [column.lag_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_module_id_05ca2da5_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_owner_id_3ae797e2_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_parent_id_3e2b159b_fk_dcim_interface_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_primary_mac_address__a0bb90ca_fk_dcim_maca" {
    columns     = [column.primary_mac_address_id]
    ref_columns = [table.dcim_macaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_qinq_svlan_id_21189a58_fk_ipam_vlan_id" {
    columns     = [column.qinq_svlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_untagged_vlan_id_838dc7be_fk_ipam_vlan_id" {
    columns     = [column.untagged_vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_vlan_translation_pol_91060031_fk_ipam_vlan" {
    columns     = [column.vlan_translation_policy_id]
    ref_columns = [table.ipam_vlantranslationpolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_vrf_id_a92e59b2_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_wireless_link_id_bc91108f_fk_wireless_" {
    columns     = [column.wireless_link_id]
    ref_columns = [table.wireless_wirelesslink.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_interface__location_id_72d5e107" {
    columns = [column._location_id]
  }
  index "dcim_interface__path_id_f8f4f7f0" {
    columns = [column._path_id]
  }
  index "dcim_interface__rack_id_0d3f84a6" {
    columns = [column._rack_id]
  }
  index "dcim_interface__site_id_0fffd4ef" {
    columns = [column._site_id]
  }
  index "dcim_interface_bridge_id_f2a8df85" {
    columns = [column.bridge_id]
  }
  index "dcim_interface_cable_id_1b264edb" {
    columns = [column.cable_id]
  }
  index "dcim_interface_device_id_359c6115" {
    columns = [column.device_id]
  }
  index "dcim_interface_lag_id_ea1a1d12" {
    columns = [column.lag_id]
  }
  index "dcim_interface_module_id_05ca2da5" {
    columns = [column.module_id]
  }
  index "dcim_interface_owner_id_3ae797e2" {
    columns = [column.owner_id]
  }
  index "dcim_interface_parent_id_3e2b159b" {
    columns = [column.parent_id]
  }
  index "dcim_interface_qinq_svlan_id_21189a58" {
    columns = [column.qinq_svlan_id]
  }
  index "dcim_interface_untagged_vlan_id_838dc7be" {
    columns = [column.untagged_vlan_id]
  }
  index "dcim_interface_vlan_translation_policy_id_91060031" {
    columns = [column.vlan_translation_policy_id]
  }
  index "dcim_interface_vrf_id_a92e59b2" {
    columns = [column.vrf_id]
  }
  index "dcim_interface_wireless_link_id_bc91108f" {
    columns = [column.wireless_link_id]
  }
  check "dcim_interface_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_interface_mtu_check" {
    expr = "(mtu >= 0)"
  }
  check "dcim_interface_speed_check" {
    expr = "(speed >= 0)"
  }
  unique "dcim_interface_primary_mac_address_id_key" {
    columns = [column.primary_mac_address_id]
  }
  unique "dcim_interface_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_interface_tagged_vlans" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "interface_id" {
    null = false
    type = bigint
  }
  column "vlan_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_interface_tagge_interface_id_5870c9e9_fk_dcim_inte" {
    columns     = [column.interface_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_tagged_vlans_vlan_id_e027005c_fk_ipam_vlan_id" {
    columns     = [column.vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_interface_tagged_vlans_interface_id_5870c9e9" {
    columns = [column.interface_id]
  }
  index "dcim_interface_tagged_vlans_vlan_id_e027005c" {
    columns = [column.vlan_id]
  }
  unique "dcim_interface_tagged_vlans_interface_id_vlan_id_0d55c576_uniq" {
    columns = [column.interface_id, column.vlan_id]
  }
}
table "dcim_interface_vdcs" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "interface_id" {
    null = false
    type = bigint
  }
  column "virtualdevicecontext_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_interface_vdcs_interface_id_6d58dbaf_fk_dcim_interface_id" {
    columns     = [column.interface_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_vdcs_virtualdevicecontext_af0bfd4b_fk_dcim_virt" {
    columns     = [column.virtualdevicecontext_id]
    ref_columns = [table.dcim_virtualdevicecontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_interface_vdcs_interface_id_6d58dbaf" {
    columns = [column.interface_id]
  }
  index "dcim_interface_vdcs_virtualdevicecontext_id_af0bfd4b" {
    columns = [column.virtualdevicecontext_id]
  }
  unique "dcim_interface_vdcs_interface_id_virtualdevi_cca9c2a6_uniq" {
    columns = [column.interface_id, column.virtualdevicecontext_id]
  }
}
table "dcim_interface_wireless_lans" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "interface_id" {
    null = false
    type = bigint
  }
  column "wirelesslan_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_interface_wirel_interface_id_80df3785_fk_dcim_inte" {
    columns     = [column.interface_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interface_wirel_wirelesslan_id_f081e278_fk_wireless_" {
    columns     = [column.wirelesslan_id]
    ref_columns = [table.wireless_wirelesslan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_interface_wireless_lans_interface_id_80df3785" {
    columns = [column.interface_id]
  }
  index "dcim_interface_wireless_lans_wirelesslan_id_f081e278" {
    columns = [column.wirelesslan_id]
  }
  unique "dcim_interface_wireless__interface_id_wirelesslan_b52fb3d8_uniq" {
    columns = [column.interface_id, column.wirelesslan_id]
  }
}
table "dcim_interfacetemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "_name" {
    null = false
    type = character_varying(100)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "mgmt_only" {
    null = false
    type = boolean
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  column "poe_mode" {
    null = true
    type = character_varying(50)
  }
  column "poe_type" {
    null = true
    type = character_varying(50)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "bridge_id" {
    null = true
    type = bigint
  }
  column "rf_role" {
    null = true
    type = character_varying(30)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_interfacetempla_bridge_id_4e44355b_fk_dcim_inte" {
    columns     = [column.bridge_id]
    ref_columns = [table.dcim_interfacetemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interfacetempla_device_type_id_4bfcbfab_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_interfacetempla_module_type_id_f941f180_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_interfacetemplate_bridge_id_4e44355b" {
    columns = [column.bridge_id]
  }
  index "dcim_interfacetemplate_device_type_id_4bfcbfab" {
    columns = [column.device_type_id]
  }
  index "dcim_interfacetemplate_module_type_id_f941f180" {
    columns = [column.module_type_id]
  }
  unique "dcim_interfacetemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_interfacetemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_inventoryitem" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "part_id" {
    null = false
    type = character_varying(50)
  }
  column "serial" {
    null = false
    type = character_varying(50)
  }
  column "asset_tag" {
    null = true
    type = character_varying(50)
  }
  column "discovered" {
    null = false
    type = boolean
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "manufacturer_id" {
    null = true
    type = bigint
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "component_id" {
    null = true
    type = bigint
  }
  column "component_type_id" {
    null = true
    type = integer
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_inventoryitem__location_id_05a23b33_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem__rack_id_25b80d23_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem__site_id_cd94573b_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_component_type_id_f0e4d83a_fk_django_co" {
    columns     = [column.component_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_device_id_033d83f8_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_manufacturer_id_dcd1b78a_fk_dcim_manu" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_owner_id_ad4332eb_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_parent_id_7ebcd457_fk_dcim_inventoryitem_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_inventoryitem.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitem_role_id_2bcfcb04_fk_dcim_inve" {
    columns     = [column.role_id]
    ref_columns = [table.dcim_inventoryitemrole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_invent_compone_0560bb_idx" {
    columns = [column.component_type_id, column.component_id]
  }
  index "dcim_inventoryitem__location_id_05a23b33" {
    columns = [column._location_id]
  }
  index "dcim_inventoryitem__rack_id_25b80d23" {
    columns = [column._rack_id]
  }
  index "dcim_inventoryitem__site_id_cd94573b" {
    columns = [column._site_id]
  }
  index "dcim_inventoryitem_asset_tag_d3289273_like" {
    on {
      column = column.asset_tag
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_inventoryitem_component_type_id_f0e4d83a" {
    columns = [column.component_type_id]
  }
  index "dcim_inventoryitem_device_id_033d83f8" {
    columns = [column.device_id]
  }
  index "dcim_inventoryitem_manufacturer_id_dcd1b78a" {
    columns = [column.manufacturer_id]
  }
  index "dcim_inventoryitem_owner_id_ad4332eb" {
    columns = [column.owner_id]
  }
  index "dcim_inventoryitem_parent_id_7ebcd457" {
    columns = [column.parent_id]
  }
  index "dcim_inventoryitem_role_id_2bcfcb04" {
    columns = [column.role_id]
  }
  index "dcim_inventoryitem_tree_id975c" {
    columns = [column.tree_id, column.lft]
  }
  index "dcim_inventoryitem_tree_id_4676ade2" {
    columns = [column.tree_id]
  }
  check "dcim_inventoryitem_component_id_check" {
    expr = "(component_id >= 0)"
  }
  check "dcim_inventoryitem_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_inventoryitem_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_inventoryitem_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_inventoryitem_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_inventoryitem_asset_tag_key" {
    columns = [column.asset_tag]
  }
  unique "dcim_inventoryitem_unique_device_parent_name" {
    columns = [column.device_id, column.parent_id, column.name]
  }
}
table "dcim_inventoryitemrole" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_inventoryitemrole_owner_id_067442e9_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_inventoryitemrole_name_4c8cfe6d_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_inventoryitemrole_owner_id_067442e9" {
    columns = [column.owner_id]
  }
  index "dcim_inventoryitemrole_slug_3556c227_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "dcim_inventoryitemrole_name_key" {
    columns = [column.name]
  }
  unique "dcim_inventoryitemrole_slug_key" {
    columns = [column.slug]
  }
}
table "dcim_inventoryitemtemplate" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "component_id" {
    null = true
    type = bigint
  }
  column "part_id" {
    null = false
    type = character_varying(50)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "component_type_id" {
    null = true
    type = integer
  }
  column "device_type_id" {
    null = false
    type = bigint
  }
  column "manufacturer_id" {
    null = true
    type = bigint
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_inventoryitemte_component_type_id_161623a2_fk_django_co" {
    columns     = [column.component_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitemte_device_type_id_6a1be904_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitemte_manufacturer_id_b388c5d9_fk_dcim_manu" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitemte_parent_id_0dac73bb_fk_dcim_inve" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_inventoryitemtemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_inventoryitemte_role_id_292676e6_fk_dcim_inve" {
    columns     = [column.role_id]
    ref_columns = [table.dcim_inventoryitemrole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_invent_compone_77b5f8_idx" {
    columns = [column.component_type_id, column.component_id]
  }
  index "dcim_inventoryitemtemplate_component_type_id_161623a2" {
    columns = [column.component_type_id]
  }
  index "dcim_inventoryitemtemplate_device_type_id_6a1be904" {
    columns = [column.device_type_id]
  }
  index "dcim_inventoryitemtemplate_manufacturer_id_b388c5d9" {
    columns = [column.manufacturer_id]
  }
  index "dcim_inventoryitemtemplate_parent_id_0dac73bb" {
    columns = [column.parent_id]
  }
  index "dcim_inventoryitemtemplate_role_id_292676e6" {
    columns = [column.role_id]
  }
  index "dcim_inventoryitemtemplate_tree_id_75ebcb8e" {
    columns = [column.tree_id]
  }
  index "dcim_inventoryitemtemplatedee0" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_inventoryitemtemplate_component_id_check" {
    expr = "(component_id >= 0)"
  }
  check "dcim_inventoryitemtemplate_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_inventoryitemtemplate_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_inventoryitemtemplate_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_inventoryitemtemplate_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_inventoryitemtemplate_unique_device_type_parent_name" {
    columns = [column.device_type_id, column.parent_id, column.name]
  }
}
table "dcim_location" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "facility" {
    null = false
    type = character_varying(50)
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_location_owner_id_919a8713_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_location_parent_id_d77f3318_fk_dcim_location_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_location_site_id_b55e975f_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_location_tenant_id_2c4df974_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_location_name" {
    unique  = true
    columns = [column.site_id, column.name]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_location_owner_id_919a8713" {
    columns = [column.owner_id]
  }
  index "dcim_location_parent_id_d77f3318" {
    columns = [column.parent_id]
  }
  index "dcim_location_site_id_b55e975f" {
    columns = [column.site_id]
  }
  index "dcim_location_slug" {
    unique  = true
    columns = [column.site_id, column.slug]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_location_slug_352c5472" {
    columns = [column.slug]
  }
  index "dcim_location_slug_352c5472_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_location_tenant_id_2c4df974" {
    columns = [column.tenant_id]
  }
  index "dcim_location_tree_id_5089ef14" {
    columns = [column.tree_id]
  }
  index "dcim_location_tree_id_lft_idx" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_location_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_location_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_location_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_location_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_location_parent_name" {
    columns = [column.site_id, column.parent_id, column.name]
  }
  unique "dcim_location_parent_slug" {
    columns = [column.site_id, column.parent_id, column.slug]
  }
}
table "dcim_macaddress" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "mac_address" {
    null = false
    type = macaddr
  }
  column "assigned_object_id" {
    null = true
    type = bigint
  }
  column "assigned_object_type_id" {
    null = true
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_macaddress_assigned_object_type_28814a20_fk_django_co" {
    columns     = [column.assigned_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_macaddress_owner_id_29ba2f60_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_macadd_assigne_54115d_idx" {
    columns = [column.assigned_object_type_id, column.assigned_object_id]
  }
  index "dcim_macaddress_assigned_object_type_id_28814a20" {
    columns = [column.assigned_object_type_id]
  }
  index "dcim_macaddress_owner_id_29ba2f60" {
    columns = [column.owner_id]
  }
  check "dcim_macaddress_assigned_object_id_check" {
    expr = "(assigned_object_id >= 0)"
  }
}
table "dcim_manufacturer" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_manufacturer_owner_id_8d78661f_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_manufacturer_name_841fcd92_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_manufacturer_owner_id_8d78661f" {
    columns = [column.owner_id]
  }
  index "dcim_manufacturer_slug_00430749_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "dcim_manufacturer_name_key" {
    columns = [column.name]
  }
  unique "dcim_manufacturer_slug_key" {
    columns = [column.slug]
  }
}
table "dcim_module" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "local_context_data" {
    null = true
    type = jsonb
  }
  column "serial" {
    null = false
    type = character_varying(50)
  }
  column "asset_tag" {
    null = true
    type = character_varying(50)
  }
  column "comments" {
    null = false
    type = text
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "module_bay_id" {
    null = false
    type = bigint
  }
  column "module_type_id" {
    null = false
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_module_device_id_53cfd5be_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_module_module_bay_id_8a1bf3e2_fk_dcim_modulebay_id" {
    columns     = [column.module_bay_id]
    ref_columns = [table.dcim_modulebay.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_module_module_type_id_a50b39fc_fk_dcim_moduletype_id" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_module_owner_id_ee6f1ef4_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_module_asset_tag_2fd91eed_like" {
    on {
      column = column.asset_tag
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_module_device_id_53cfd5be" {
    columns = [column.device_id]
  }
  index "dcim_module_module_type_id_a50b39fc" {
    columns = [column.module_type_id]
  }
  index "dcim_module_owner_id_ee6f1ef4" {
    columns = [column.owner_id]
  }
  unique "dcim_module_asset_tag_key" {
    columns = [column.asset_tag]
  }
  unique "dcim_module_module_bay_id_key" {
    columns = [column.module_bay_id]
  }
}
table "dcim_modulebay" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "position" {
    null = false
    type = character_varying(30)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "level" {
    null = false
    type = integer
  }
  column "lft" {
    null = false
    type = integer
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_modulebay__location_id_17290069_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay__rack_id_673d8fb5_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay__site_id_cedd61bc_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay_device_id_3526abc2_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay_module_id_a21ddd9a_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay_owner_id_311f58c6_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebay_parent_id_e483f9b7_fk_dcim_modulebay_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_modulebay.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_modulebay__location_id_17290069" {
    columns = [column._location_id]
  }
  index "dcim_modulebay__rack_id_673d8fb5" {
    columns = [column._rack_id]
  }
  index "dcim_modulebay__site_id_cedd61bc" {
    columns = [column._site_id]
  }
  index "dcim_modulebay_device_id_3526abc2" {
    columns = [column.device_id]
  }
  index "dcim_modulebay_module_id_a21ddd9a" {
    columns = [column.module_id]
  }
  index "dcim_modulebay_owner_id_311f58c6" {
    columns = [column.owner_id]
  }
  index "dcim_modulebay_parent_id_e483f9b7" {
    columns = [column.parent_id]
  }
  index "dcim_modulebay_tree_id_223db581" {
    columns = [column.tree_id]
  }
  index "dcim_modulebay_tree_id_lft_idx" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_modulebay_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_modulebay_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_modulebay_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_modulebay_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_modulebay_unique_device_module_name" {
    columns = [column.device_id, column.module_id, column.name]
  }
}
table "dcim_modulebaytemplate" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "position" {
    null = false
    type = character_varying(30)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_modulebaytempla_device_type_id_9eaf9bd3_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_modulebaytempla_module_type_id_2fdfb491_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_modulebaytemplate_device_type_id_9eaf9bd3" {
    columns = [column.device_type_id]
  }
  index "dcim_modulebaytemplate_module_type_id_2fdfb491" {
    columns = [column.module_type_id]
  }
  unique "dcim_modulebaytemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_modulebaytemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_moduletype" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "model" {
    null = false
    type = character_varying(100)
  }
  column "part_number" {
    null = false
    type = character_varying(50)
  }
  column "comments" {
    null = false
    type = text
  }
  column "manufacturer_id" {
    null = false
    type = bigint
  }
  column "weight" {
    null = true
    type = numeric(8,2)
  }
  column "weight_unit" {
    null = true
    type = character_varying(50)
  }
  column "_abs_weight" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "airflow" {
    null = true
    type = character_varying(50)
  }
  column "attribute_data" {
    null = true
    type = jsonb
  }
  column "profile_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "module_count" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_moduletype_manufacturer_id_7347392e_fk_dcim_manu" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_moduletype_owner_id_2ea2fd3b_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_moduletype_profile_id_62b5d02d_fk_dcim_modu" {
    columns     = [column.profile_id]
    ref_columns = [table.dcim_moduletypeprofile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_moduletype_manufacturer_id_7347392e" {
    columns = [column.manufacturer_id]
  }
  index "dcim_moduletype_owner_id_2ea2fd3b" {
    columns = [column.owner_id]
  }
  index "dcim_moduletype_profile_id_62b5d02d" {
    columns = [column.profile_id]
  }
  check "dcim_moduletype__abs_weight_check" {
    expr = "(_abs_weight >= 0)"
  }
  unique "dcim_moduletype_unique_manufacturer_model" {
    columns = [column.manufacturer_id, column.model]
  }
}
table "dcim_moduletypeprofile" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "schema" {
    null = true
    type = jsonb
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_moduletypeprofile_owner_id_c4488ff6_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_moduletypeprofile_name_1709c36e_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_moduletypeprofile_owner_id_c4488ff6" {
    columns = [column.owner_id]
  }
  unique "dcim_moduletypeprofile_name_key" {
    columns = [column.name]
  }
}
table "dcim_platform" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "manufacturer_id" {
    null = true
    type = bigint
  }
  column "config_template_id" {
    null = true
    type = bigint
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "level" {
    null = false
    type = integer
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_platform_config_template_id_013a4d3c_fk_extras_co" {
    columns     = [column.config_template_id]
    ref_columns = [table.extras_configtemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_platform_manufacturer_id_83f72d3d_fk_dcim_manufacturer_id" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_platform_owner_id_0990eb87_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_platform_parent_id_795c7101_fk_dcim_platform_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_platform.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_platform_config_template_id_013a4d3c" {
    columns = [column.config_template_id]
  }
  index "dcim_platform_manufacturer_id_83f72d3d" {
    columns = [column.manufacturer_id]
  }
  index "dcim_platform_name" {
    unique  = true
    columns = [column.name]
    where   = "(manufacturer_id IS NULL)"
  }
  index "dcim_platform_owner_id_0990eb87" {
    columns = [column.owner_id]
  }
  index "dcim_platform_parent_id_795c7101" {
    columns = [column.parent_id]
  }
  index "dcim_platform_slug" {
    unique  = true
    columns = [column.slug]
    where   = "(manufacturer_id IS NULL)"
  }
  index "dcim_platform_slug_b0908ae4" {
    columns = [column.slug]
  }
  index "dcim_platform_slug_b0908ae4_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_platform_tree_id_ca32aeb8" {
    columns = [column.tree_id]
  }
  index "dcim_platform_tree_id_lft_idx" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_platform_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_platform_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_platform_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_platform_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_platform_manufacturer_name" {
    columns = [column.manufacturer_id, column.name]
  }
  unique "dcim_platform_manufacturer_slug" {
    columns = [column.manufacturer_id, column.slug]
  }
}
table "dcim_portmapping" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "front_port_position" {
    null = false
    type = smallint
  }
  column "rear_port_position" {
    null = false
    type = smallint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "front_port_id" {
    null = false
    type = bigint
  }
  column "rear_port_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_portmapping_device_id_eb86e378_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_portmapping_front_port_id_d8413d45_fk_dcim_frontport_id" {
    columns     = [column.front_port_id]
    ref_columns = [table.dcim_frontport.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_portmapping_rear_port_id_dc3fb4b8_fk_dcim_rearport_id" {
    columns     = [column.rear_port_id]
    ref_columns = [table.dcim_rearport.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_portmapping_device_id_eb86e378" {
    columns = [column.device_id]
  }
  index "dcim_portmapping_front_port_id_d8413d45" {
    columns = [column.front_port_id]
  }
  index "dcim_portmapping_rear_port_id_dc3fb4b8" {
    columns = [column.rear_port_id]
  }
  check "dcim_portmapping_front_port_position_check" {
    expr = "(front_port_position >= 0)"
  }
  check "dcim_portmapping_rear_port_position_check" {
    expr = "(rear_port_position >= 0)"
  }
  unique "dcim_portmapping_unique_front_port_position" {
    columns = [column.front_port_id, column.front_port_position]
  }
  unique "dcim_portmapping_unique_rear_port_position" {
    columns = [column.rear_port_id, column.rear_port_position]
  }
}
table "dcim_porttemplatemapping" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "front_port_position" {
    null = false
    type = smallint
  }
  column "rear_port_position" {
    null = false
    type = smallint
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  column "front_port_id" {
    null = false
    type = bigint
  }
  column "rear_port_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_porttemplatemap_device_type_id_dede0eeb_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_porttemplatemap_front_port_id_090c3c11_fk_dcim_fron" {
    columns     = [column.front_port_id]
    ref_columns = [table.dcim_frontporttemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_porttemplatemap_module_type_id_3a84e529_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_porttemplatemap_rear_port_id_93a9b08f_fk_dcim_rear" {
    columns     = [column.rear_port_id]
    ref_columns = [table.dcim_rearporttemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_porttemplatemapping_device_type_id_dede0eeb" {
    columns = [column.device_type_id]
  }
  index "dcim_porttemplatemapping_front_port_id_090c3c11" {
    columns = [column.front_port_id]
  }
  index "dcim_porttemplatemapping_module_type_id_3a84e529" {
    columns = [column.module_type_id]
  }
  index "dcim_porttemplatemapping_rear_port_id_93a9b08f" {
    columns = [column.rear_port_id]
  }
  check "dcim_porttemplatemapping_front_port_position_check" {
    expr = "(front_port_position >= 0)"
  }
  check "dcim_porttemplatemapping_rear_port_position_check" {
    expr = "(rear_port_position >= 0)"
  }
  unique "dcim_porttemplatemapping_unique_front_port_position" {
    columns = [column.front_port_id, column.front_port_position]
  }
  unique "dcim_porttemplatemapping_unique_rear_port_position" {
    columns = [column.rear_port_id, column.rear_port_position]
  }
}
table "dcim_powerfeed" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "supply" {
    null = false
    type = character_varying(50)
  }
  column "phase" {
    null = false
    type = character_varying(50)
  }
  column "voltage" {
    null = false
    type = smallint
  }
  column "amperage" {
    null = false
    type = smallint
  }
  column "max_utilization" {
    null = false
    type = smallint
  }
  column "available_power" {
    null = false
    type = integer
  }
  column "comments" {
    null = false
    type = text
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "power_panel_id" {
    null = false
    type = bigint
  }
  column "rack_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_powerfeed__path_id_a1ea1f28_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerfeed_cable_id_ec44c4f8_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerfeed_owner_id_97320081_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerfeed_power_panel_id_32bde3be_fk_dcim_powerpanel_id" {
    columns     = [column.power_panel_id]
    ref_columns = [table.dcim_powerpanel.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerfeed_rack_id_7abba090_fk_dcim_rack_id" {
    columns     = [column.rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerfeed_tenant_id_947bee85_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_powerfeed__path_id_a1ea1f28" {
    columns = [column._path_id]
  }
  index "dcim_powerfeed_cable_id_ec44c4f8" {
    columns = [column.cable_id]
  }
  index "dcim_powerfeed_owner_id_97320081" {
    columns = [column.owner_id]
  }
  index "dcim_powerfeed_power_panel_id_32bde3be" {
    columns = [column.power_panel_id]
  }
  index "dcim_powerfeed_rack_id_7abba090" {
    columns = [column.rack_id]
  }
  index "dcim_powerfeed_tenant_id_947bee85" {
    columns = [column.tenant_id]
  }
  check "dcim_powerfeed_amperage_check" {
    expr = "(amperage >= 0)"
  }
  check "dcim_powerfeed_available_power_check" {
    expr = "(available_power >= 0)"
  }
  check "dcim_powerfeed_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_powerfeed_max_utilization_check" {
    expr = "(max_utilization >= 0)"
  }
  unique "dcim_powerfeed_unique_power_panel_name" {
    columns = [column.power_panel_id, column.name]
  }
}
table "dcim_poweroutlet" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "feed_leg" {
    null = true
    type = character_varying(50)
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "power_port_id" {
    null = true
    type = bigint
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_poweroutlet__location_id_49563316_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet__path_id_cbb47bb9_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet__rack_id_aca89672_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet__site_id_a956755e_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet_cable_id_8dbea1ec_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet_device_id_286351d7_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet_module_id_032f5af2_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet_owner_id_0806d01d_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlet_power_port_id_9bdf4163_fk_dcim_powerport_id" {
    columns     = [column.power_port_id]
    ref_columns = [table.dcim_powerport.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_poweroutlet__location_id_49563316" {
    columns = [column._location_id]
  }
  index "dcim_poweroutlet__path_id_cbb47bb9" {
    columns = [column._path_id]
  }
  index "dcim_poweroutlet__rack_id_aca89672" {
    columns = [column._rack_id]
  }
  index "dcim_poweroutlet__site_id_a956755e" {
    columns = [column._site_id]
  }
  index "dcim_poweroutlet_cable_id_8dbea1ec" {
    columns = [column.cable_id]
  }
  index "dcim_poweroutlet_device_id_286351d7" {
    columns = [column.device_id]
  }
  index "dcim_poweroutlet_module_id_032f5af2" {
    columns = [column.module_id]
  }
  index "dcim_poweroutlet_owner_id_0806d01d" {
    columns = [column.owner_id]
  }
  index "dcim_poweroutlet_power_port_id_9bdf4163" {
    columns = [column.power_port_id]
  }
  check "dcim_poweroutlet_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  unique "dcim_poweroutlet_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_poweroutlettemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "feed_leg" {
    null = true
    type = character_varying(50)
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "power_port_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_poweroutlettemp_device_type_id_26b2316c_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlettemp_module_type_id_6142b416_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_poweroutlettemp_power_port_id_c0fb0c42_fk_dcim_powe" {
    columns     = [column.power_port_id]
    ref_columns = [table.dcim_powerporttemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_poweroutlettemplate_device_type_id_26b2316c" {
    columns = [column.device_type_id]
  }
  index "dcim_poweroutlettemplate_module_type_id_6142b416" {
    columns = [column.module_type_id]
  }
  index "dcim_poweroutlettemplate_power_port_id_c0fb0c42" {
    columns = [column.power_port_id]
  }
  unique "dcim_poweroutlettemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_poweroutlettemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_powerpanel" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "location_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = false
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_powerpanel_location_id_474b60f8_fk_dcim_location_id" {
    columns     = [column.location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerpanel_owner_id_11e7d421_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerpanel_site_id_c430bc89_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_powerpanel_location_id_474b60f8" {
    columns = [column.location_id]
  }
  index "dcim_powerpanel_owner_id_11e7d421" {
    columns = [column.owner_id]
  }
  index "dcim_powerpanel_site_id_c430bc89" {
    columns = [column.site_id]
  }
  unique "dcim_powerpanel_unique_site_name" {
    columns = [column.site_id, column.name]
  }
}
table "dcim_powerport" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "maximum_draw" {
    null = true
    type = integer
  }
  column "allocated_draw" {
    null = true
    type = integer
  }
  column "_path_id" {
    null = true
    type = bigint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_powerport__location_id_ccf995e7_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport__path_id_9fe4af8f_fk_dcim_cablepath_id" {
    columns     = [column._path_id]
    ref_columns = [table.dcim_cablepath.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport__rack_id_4c1c316d_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport__site_id_87bfa142_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport_cable_id_c9682ba2_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport_device_id_ef7185ae_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport_module_id_d0c27534_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerport_owner_id_b83ff931_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_powerport__location_id_ccf995e7" {
    columns = [column._location_id]
  }
  index "dcim_powerport__path_id_9fe4af8f" {
    columns = [column._path_id]
  }
  index "dcim_powerport__rack_id_4c1c316d" {
    columns = [column._rack_id]
  }
  index "dcim_powerport__site_id_87bfa142" {
    columns = [column._site_id]
  }
  index "dcim_powerport_cable_id_c9682ba2" {
    columns = [column.cable_id]
  }
  index "dcim_powerport_device_id_ef7185ae" {
    columns = [column.device_id]
  }
  index "dcim_powerport_module_id_d0c27534" {
    columns = [column.module_id]
  }
  index "dcim_powerport_owner_id_b83ff931" {
    columns = [column.owner_id]
  }
  check "dcim_powerport_allocated_draw_check" {
    expr = "(allocated_draw >= 0)"
  }
  check "dcim_powerport_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_powerport_maximum_draw_check" {
    expr = "(maximum_draw >= 0)"
  }
  unique "dcim_powerport_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_powerporttemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = true
    type = character_varying(50)
  }
  column "maximum_draw" {
    null = true
    type = integer
  }
  column "allocated_draw" {
    null = true
    type = integer
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_powerporttempla_device_type_id_1ddfbfcc_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_powerporttempla_module_type_id_93e26849_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_powerporttemplate_device_type_id_1ddfbfcc" {
    columns = [column.device_type_id]
  }
  index "dcim_powerporttemplate_module_type_id_93e26849" {
    columns = [column.module_type_id]
  }
  check "dcim_powerporttemplate_allocated_draw_check" {
    expr = "(allocated_draw >= 0)"
  }
  check "dcim_powerporttemplate_maximum_draw_check" {
    expr = "(maximum_draw >= 0)"
  }
  unique "dcim_powerporttemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_powerporttemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_rack" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "facility_id" {
    null = true
    type = character_varying(50)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "serial" {
    null = false
    type = character_varying(50)
  }
  column "asset_tag" {
    null = true
    type = character_varying(50)
  }
  column "form_factor" {
    null = true
    type = character_varying(50)
  }
  column "width" {
    null = false
    type = smallint
  }
  column "u_height" {
    null = false
    type = smallint
  }
  column "desc_units" {
    null = false
    type = boolean
  }
  column "outer_width" {
    null = true
    type = smallint
  }
  column "outer_depth" {
    null = true
    type = smallint
  }
  column "outer_unit" {
    null = true
    type = character_varying(50)
  }
  column "comments" {
    null = false
    type = text
  }
  column "location_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "weight" {
    null = true
    type = numeric(8,2)
  }
  column "max_weight" {
    null = true
    type = integer
  }
  column "weight_unit" {
    null = true
    type = character_varying(50)
  }
  column "_abs_weight" {
    null = true
    type = bigint
  }
  column "_abs_max_weight" {
    null = true
    type = bigint
  }
  column "mounting_depth" {
    null = true
    type = smallint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "starting_unit" {
    null = false
    type = smallint
  }
  column "rack_type_id" {
    null = true
    type = bigint
  }
  column "airflow" {
    null = true
    type = character_varying(50)
  }
  column "outer_height" {
    null = true
    type = smallint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_rack_location_id_5f63ec31_fk_dcim_location_id" {
    columns     = [column.location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rack_owner_id_7a5532fc_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rack_rack_type_id_39433a22_fk_dcim_racktype_id" {
    columns     = [column.rack_type_id]
    ref_columns = [table.dcim_racktype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rack_role_id_62d6919e_fk_dcim_rackrole_id" {
    columns     = [column.role_id]
    ref_columns = [table.dcim_rackrole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rack_site_id_403c7b3a_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rack_tenant_id_7cdf3725_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_rack_asset_tag_f88408e5_like" {
    on {
      column = column.asset_tag
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_rack_location_id_5f63ec31" {
    columns = [column.location_id]
  }
  index "dcim_rack_owner_id_7a5532fc" {
    columns = [column.owner_id]
  }
  index "dcim_rack_rack_type_id_39433a22" {
    columns = [column.rack_type_id]
  }
  index "dcim_rack_role_id_62d6919e" {
    columns = [column.role_id]
  }
  index "dcim_rack_site_id_403c7b3a" {
    columns = [column.site_id]
  }
  index "dcim_rack_tenant_id_7cdf3725" {
    columns = [column.tenant_id]
  }
  check "dcim_rack__abs_max_weight_check" {
    expr = "(_abs_max_weight >= 0)"
  }
  check "dcim_rack__abs_weight_check" {
    expr = "(_abs_weight >= 0)"
  }
  check "dcim_rack_max_weight_check" {
    expr = "(max_weight >= 0)"
  }
  check "dcim_rack_mounting_depth_check" {
    expr = "(mounting_depth >= 0)"
  }
  check "dcim_rack_outer_depth_check" {
    expr = "(outer_depth >= 0)"
  }
  check "dcim_rack_outer_height_check" {
    expr = "(outer_height >= 0)"
  }
  check "dcim_rack_outer_width_check" {
    expr = "(outer_width >= 0)"
  }
  check "dcim_rack_starting_unit_check" {
    expr = "(starting_unit >= 0)"
  }
  check "dcim_rack_u_height_check" {
    expr = "(u_height >= 0)"
  }
  check "dcim_rack_width_check" {
    expr = "(width >= 0)"
  }
  unique "dcim_rack_asset_tag_key" {
    columns = [column.asset_tag]
  }
  unique "dcim_rack_unique_location_facility_id" {
    columns = [column.location_id, column.facility_id]
  }
  unique "dcim_rack_unique_location_name" {
    columns = [column.location_id, column.name]
  }
}
table "dcim_rackreservation" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "units" {
    null = false
    type = sql("smallint[]")
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "rack_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_rackreservation_owner_id_12c19e94_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rackreservation_rack_id_1ebbaa9b_fk_dcim_rack_id" {
    columns     = [column.rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rackreservation_tenant_id_eb5e045f_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rackreservation_user_id_0785a527_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_rackreservation_owner_id_12c19e94" {
    columns = [column.owner_id]
  }
  index "dcim_rackreservation_rack_id_1ebbaa9b" {
    columns = [column.rack_id]
  }
  index "dcim_rackreservation_tenant_id_eb5e045f" {
    columns = [column.tenant_id]
  }
  index "dcim_rackreservation_user_id_0785a527" {
    columns = [column.user_id]
  }
}
table "dcim_rackrole" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_rackrole_owner_id_fb6f0b77_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_rackrole_name_9077cfcc_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_rackrole_owner_id_fb6f0b77" {
    columns = [column.owner_id]
  }
  index "dcim_rackrole_slug_40bbcd3a_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "dcim_rackrole_name_key" {
    columns = [column.name]
  }
  unique "dcim_rackrole_slug_key" {
    columns = [column.slug]
  }
}
table "dcim_racktype" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "weight" {
    null = true
    type = numeric(8,2)
  }
  column "weight_unit" {
    null = true
    type = character_varying(50)
  }
  column "_abs_weight" {
    null = true
    type = bigint
  }
  column "manufacturer_id" {
    null = false
    type = bigint
  }
  column "model" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "form_factor" {
    null = false
    type = character_varying(50)
  }
  column "width" {
    null = false
    type = smallint
  }
  column "u_height" {
    null = false
    type = smallint
  }
  column "starting_unit" {
    null = false
    type = smallint
  }
  column "desc_units" {
    null = false
    type = boolean
  }
  column "outer_width" {
    null = true
    type = smallint
  }
  column "outer_depth" {
    null = true
    type = smallint
  }
  column "outer_unit" {
    null = true
    type = character_varying(50)
  }
  column "max_weight" {
    null = true
    type = integer
  }
  column "_abs_max_weight" {
    null = true
    type = bigint
  }
  column "mounting_depth" {
    null = true
    type = smallint
  }
  column "outer_height" {
    null = true
    type = smallint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "rack_count" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_racktype_manufacturer_id_d46a05c6_fk_dcim_manufacturer_id" {
    columns     = [column.manufacturer_id]
    ref_columns = [table.dcim_manufacturer.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_racktype_owner_id_ce0a0d75_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_racktype_manufacturer_id_d46a05c6" {
    columns = [column.manufacturer_id]
  }
  index "dcim_racktype_owner_id_ce0a0d75" {
    columns = [column.owner_id]
  }
  index "dcim_racktype_slug_6bbb384a_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "dcim_racktype__abs_max_weight_check" {
    expr = "(_abs_max_weight >= 0)"
  }
  check "dcim_racktype__abs_weight_check" {
    expr = "(_abs_weight >= 0)"
  }
  check "dcim_racktype_max_weight_check" {
    expr = "(max_weight >= 0)"
  }
  check "dcim_racktype_mounting_depth_check" {
    expr = "(mounting_depth >= 0)"
  }
  check "dcim_racktype_outer_depth_check" {
    expr = "(outer_depth >= 0)"
  }
  check "dcim_racktype_outer_height_check" {
    expr = "(outer_height >= 0)"
  }
  check "dcim_racktype_outer_width_check" {
    expr = "(outer_width >= 0)"
  }
  check "dcim_racktype_starting_unit_check" {
    expr = "(starting_unit >= 0)"
  }
  check "dcim_racktype_u_height_check" {
    expr = "(u_height >= 0)"
  }
  check "dcim_racktype_width_check" {
    expr = "(width >= 0)"
  }
  unique "dcim_racktype_slug_key" {
    columns = [column.slug]
  }
  unique "dcim_racktype_unique_manufacturer_model" {
    columns = [column.manufacturer_id, column.model]
  }
  unique "dcim_racktype_unique_manufacturer_slug" {
    columns = [column.manufacturer_id, column.slug]
  }
}
table "dcim_rearport" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "mark_connected" {
    null = false
    type = boolean
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "positions" {
    null = false
    type = smallint
  }
  column "cable_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = false
    type = bigint
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "module_id" {
    null = true
    type = bigint
  }
  column "cable_end" {
    null = true
    type = character_varying(1)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_rack_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "cable_connector" {
    null = true
    type = smallint
  }
  column "cable_positions" {
    null = true
    type = sql("smallint[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_rearport__location_id_72554006_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport__rack_id_9af9a402_fk_dcim_rack_id" {
    columns     = [column._rack_id]
    ref_columns = [table.dcim_rack.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport__site_id_35e05ccf_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport_cable_id_42c0e4e7_fk_dcim_cable_id" {
    columns     = [column.cable_id]
    ref_columns = [table.dcim_cable.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport_device_id_0bdfe9c0_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport_module_id_9a7b7e91_fk_dcim_module_id" {
    columns     = [column.module_id]
    ref_columns = [table.dcim_module.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearport_owner_id_51174512_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_rearport__location_id_72554006" {
    columns = [column._location_id]
  }
  index "dcim_rearport__rack_id_9af9a402" {
    columns = [column._rack_id]
  }
  index "dcim_rearport__site_id_35e05ccf" {
    columns = [column._site_id]
  }
  index "dcim_rearport_cable_id_42c0e4e7" {
    columns = [column.cable_id]
  }
  index "dcim_rearport_device_id_0bdfe9c0" {
    columns = [column.device_id]
  }
  index "dcim_rearport_module_id_9a7b7e91" {
    columns = [column.module_id]
  }
  index "dcim_rearport_owner_id_51174512" {
    columns = [column.owner_id]
  }
  check "dcim_rearport_cable_connector_check" {
    expr = "(cable_connector >= 0)"
  }
  check "dcim_rearport_positions_check" {
    expr = "(positions >= 0)"
  }
  unique "dcim_rearport_unique_device_name" {
    columns = [column.device_id, column.name]
  }
}
table "dcim_rearporttemplate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
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
  column "label" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "positions" {
    null = false
    type = smallint
  }
  column "device_type_id" {
    null = true
    type = bigint
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "module_type_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_rearporttemplat_device_type_id_6a02fd01_fk_dcim_devi" {
    columns     = [column.device_type_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_rearporttemplat_module_type_id_4d970e5b_fk_dcim_modu" {
    columns     = [column.module_type_id]
    ref_columns = [table.dcim_moduletype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_rearporttemplate_device_type_id_6a02fd01" {
    columns = [column.device_type_id]
  }
  index "dcim_rearporttemplate_module_type_id_4d970e5b" {
    columns = [column.module_type_id]
  }
  check "dcim_rearporttemplate_positions_check" {
    expr = "(positions >= 0)"
  }
  unique "dcim_rearporttemplate_unique_device_type_name" {
    columns = [column.device_type_id, column.name]
  }
  unique "dcim_rearporttemplate_unique_module_type_name" {
    columns = [column.module_type_id, column.name]
  }
}
table "dcim_region" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_region_owner_id_7e9d3adf_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_region_parent_id_2486f5d4_fk_dcim_region_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_region_name" {
    unique  = true
    columns = [column.name]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_region_owner_id_7e9d3adf" {
    columns = [column.owner_id]
  }
  index "dcim_region_parent_id_2486f5d4" {
    columns = [column.parent_id]
  }
  index "dcim_region_slug" {
    unique  = true
    columns = [column.slug]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_region_slug_ff078a66" {
    columns = [column.slug]
  }
  index "dcim_region_slug_ff078a66_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_region_tree_id_a09ea9a7" {
    columns = [column.tree_id]
  }
  index "dcim_region_tree_id_lft_idx" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_region_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_region_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_region_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_region_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_region_parent_name" {
    columns = [column.parent_id, column.name]
  }
  unique "dcim_region_parent_slug" {
    columns = [column.parent_id, column.slug]
  }
}
table "dcim_site" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "facility" {
    null = false
    type = character_varying(50)
  }
  column "time_zone" {
    null = true
    type = character_varying(63)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "physical_address" {
    null = false
    type = character_varying(200)
  }
  column "shipping_address" {
    null = false
    type = character_varying(200)
  }
  column "latitude" {
    null = true
    type = numeric(8,6)
  }
  column "longitude" {
    null = true
    type = numeric(9,6)
  }
  column "comments" {
    null = false
    type = text
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "region_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_site_group_id_3910c975_fk_dcim_sitegroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_site_owner_id_ef94687e_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_site_region_id_45210932_fk_dcim_region_id" {
    columns     = [column.region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_site_tenant_id_15e7df63_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_site_group_id_3910c975" {
    columns = [column.group_id]
  }
  index "dcim_site_name_8fe66c76_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_site_owner_id_ef94687e" {
    columns = [column.owner_id]
  }
  index "dcim_site_region_id_45210932" {
    columns = [column.region_id]
  }
  index "dcim_site_slug_4412c762_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_site_tenant_id_15e7df63" {
    columns = [column.tenant_id]
  }
  unique "dcim_site_name_key" {
    columns = [column.name]
  }
  unique "dcim_site_slug_key" {
    columns = [column.slug]
  }
}
table "dcim_site_asns" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "site_id" {
    null = false
    type = bigint
  }
  column "asn_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_site_asns_asn_id_3cfd0f00_fk_ipam_asn_id" {
    columns     = [column.asn_id]
    ref_columns = [table.ipam_asn.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_site_asns_site_id_112ccacf_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_site_asns_asn_id_3cfd0f00" {
    columns = [column.asn_id]
  }
  index "dcim_site_asns_site_id_112ccacf" {
    columns = [column.site_id]
  }
  unique "dcim_site_asns_site_id_asn_id_1a5a6f23_uniq" {
    columns = [column.site_id, column.asn_id]
  }
}
table "dcim_sitegroup" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_sitegroup_owner_id_50283a64_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_sitegroup_parent_id_533a5e44_fk_dcim_sitegroup_id" {
    columns     = [column.parent_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_sitegroup_name" {
    unique  = true
    columns = [column.name]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_sitegroup_owner_id_50283a64" {
    columns = [column.owner_id]
  }
  index "dcim_sitegroup_parent_id_533a5e44" {
    columns = [column.parent_id]
  }
  index "dcim_sitegroup_slug" {
    unique  = true
    columns = [column.slug]
    where   = "(parent_id IS NULL)"
  }
  index "dcim_sitegroup_slug_a11d2b04" {
    columns = [column.slug]
  }
  index "dcim_sitegroup_slug_a11d2b04_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "dcim_sitegroup_tree_id_e76dc999" {
    columns = [column.tree_id]
  }
  index "dcim_sitegroup_tree_id_lft_idx" {
    columns = [column.tree_id, column.lft]
  }
  check "dcim_sitegroup_level_check" {
    expr = "(level >= 0)"
  }
  check "dcim_sitegroup_lft_check" {
    expr = "(lft >= 0)"
  }
  check "dcim_sitegroup_rght_check" {
    expr = "(rght >= 0)"
  }
  check "dcim_sitegroup_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "dcim_sitegroup_parent_name" {
    columns = [column.parent_id, column.name]
  }
  unique "dcim_sitegroup_parent_slug" {
    columns = [column.parent_id, column.slug]
  }
}
table "dcim_virtualchassis" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
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
  column "domain" {
    null = false
    type = character_varying(30)
  }
  column "master_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "member_count" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_virtualchassis_master_id_ab54cfc6_fk_dcim_device_id" {
    columns     = [column.master_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_virtualchassis_owner_id_76116efe_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_virtualchassis_owner_id_76116efe" {
    columns = [column.owner_id]
  }
  unique "dcim_virtualchassis_master_id_key" {
    columns = [column.master_id]
  }
}
table "dcim_virtualdevicecontext" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "identifier" {
    null = true
    type = smallint
  }
  column "comments" {
    null = false
    type = text
  }
  column "device_id" {
    null = true
    type = bigint
  }
  column "primary_ip4_id" {
    null = true
    type = bigint
  }
  column "primary_ip6_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "dcim_virtualdeviceco_primary_ip4_id_6bd0605b_fk_ipam_ipad" {
    columns     = [column.primary_ip4_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_virtualdeviceco_primary_ip6_id_ed3b81bd_fk_ipam_ipad" {
    columns     = [column.primary_ip6_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_virtualdeviceco_tenant_id_b6a21753_fk_tenancy_t" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_virtualdevicecontext_device_id_4f39274b_fk_dcim_device_id" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "dcim_virtualdevicecontext_owner_id_33c19ef7_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "dcim_virtualdevicecontext_device_id_4f39274b" {
    columns = [column.device_id]
  }
  index "dcim_virtualdevicecontext_owner_id_33c19ef7" {
    columns = [column.owner_id]
  }
  index "dcim_virtualdevicecontext_tenant_id_b6a21753" {
    columns = [column.tenant_id]
  }
  check "dcim_virtualdevicecontext_identifier_check" {
    expr = "(identifier >= 0)"
  }
  unique "dcim_virtualdevicecontext_device_identifier" {
    columns = [column.device_id, column.identifier]
  }
  unique "dcim_virtualdevicecontext_device_name" {
    columns = [column.device_id, column.name]
  }
  unique "dcim_virtualdevicecontext_primary_ip4_id_key" {
    columns = [column.primary_ip4_id]
  }
  unique "dcim_virtualdevicecontext_primary_ip6_id_key" {
    columns = [column.primary_ip6_id]
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
table "extras_bookmark" {
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
  column "object_id" {
    null = false
    type = bigint
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_bookmark_object_type_id_18c4bb44_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_bookmark_user_id_cb6c6677_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_book_object__2df6b4_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "extras_bookmark_object_type_id_18c4bb44" {
    columns = [column.object_type_id]
  }
  index "extras_bookmark_user_id_cb6c6677" {
    columns = [column.user_id]
  }
  check "extras_bookmark_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "extras_bookmark_unique_per_object_and_user" {
    columns = [column.object_type_id, column.object_id, column.user_id]
  }
}
table "extras_cachedvalue" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "timestamp" {
    null = false
    type = timestamptz
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "field" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = false
    type = character_varying(30)
  }
  column "value" {
    null = false
    type = text
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_cachedvalue_object_type_id_6f47d444_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_cachedvalue_object" {
    columns = [column.object_type_id, column.object_id]
  }
  index "extras_cachedvalue_object_type_id_6f47d444" {
    columns = [column.object_type_id]
  }
  check "extras_cachedvalue_object_id_check" {
    expr = "(object_id >= 0)"
  }
  check "extras_cachedvalue_weight_check" {
    expr = "(weight >= 0)"
  }
}
table "extras_configcontext" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "data_file_id" {
    null = true
    type = bigint
  }
  column "data_path" {
    null = false
    type = character_varying(1000)
  }
  column "data_source_id" {
    null = true
    type = bigint
  }
  column "auto_sync_enabled" {
    null = false
    type = boolean
  }
  column "data_synced" {
    null = true
    type = timestamptz
  }
  column "profile_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_data_file_id_8fdd620b_fk_core_datafile_id" {
    columns     = [column.data_file_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_data_source_id_1b2eb8af_fk_core_data" {
    columns     = [column.data_source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_owner_id_6c8d9a06_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_profile_id_48c7bc6a_fk_extras_co" {
    columns     = [column.profile_id]
    ref_columns = [table.extras_configcontextprofile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_data_file_id_8fdd620b" {
    columns = [column.data_file_id]
  }
  index "extras_configcontext_data_source_id_1b2eb8af" {
    columns = [column.data_source_id]
  }
  index "extras_configcontext_name_4bbfe25d_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_configcontext_owner_id_6c8d9a06" {
    columns = [column.owner_id]
  }
  index "extras_configcontext_profile_id_48c7bc6a" {
    columns = [column.profile_id]
  }
  check "extras_configcontext_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "extras_configcontext_name_key" {
    columns = [column.name]
  }
}
table "extras_configcontext_cluster_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "clustergroup_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_clustergroup_id_f4322ce8_fk_virtualiz" {
    columns     = [column.clustergroup_id]
    ref_columns = [table.virtualization_clustergroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_configcontext_id_8f50b794_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_cluster_groups_clustergroup_id_f4322ce8" {
    columns = [column.clustergroup_id]
  }
  index "extras_configcontext_cluster_groups_configcontext_id_8f50b794" {
    columns = [column.configcontext_id]
  }
  unique "extras_configcontext_clu_configcontext_id_cluster_bc530192_uniq" {
    columns = [column.configcontext_id, column.clustergroup_id]
  }
}
table "extras_configcontext_cluster_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "clustertype_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_clustertype_id_fa493b64_fk_virtualiz" {
    columns     = [column.clustertype_id]
    ref_columns = [table.virtualization_clustertype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_configcontext_id_d549b6f2_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_cluster_types_clustertype_id_fa493b64" {
    columns = [column.clustertype_id]
  }
  index "extras_configcontext_cluster_types_configcontext_id_d549b6f2" {
    columns = [column.configcontext_id]
  }
  unique "extras_configcontext_clu_configcontext_id_cluster_4a2d5e56_uniq" {
    columns = [column.configcontext_id, column.clustertype_id]
  }
}
table "extras_configcontext_clusters" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "cluster_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_cluster_id_6abd47a1_fk_virtualiz" {
    columns     = [column.cluster_id]
    ref_columns = [table.virtualization_cluster.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_configcontext_id_ed579a40_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_clusters_cluster_id_6abd47a1" {
    columns = [column.cluster_id]
  }
  index "extras_configcontext_clusters_configcontext_id_ed579a40" {
    columns = [column.configcontext_id]
  }
  unique "extras_configcontext_clu_configcontext_id_cluster_0c7e5d20_uniq" {
    columns = [column.configcontext_id, column.cluster_id]
  }
}
table "extras_configcontext_device_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "devicetype_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_55632923_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_devicetype_id_b8788c2d_fk_dcim_devi" {
    columns     = [column.devicetype_id]
    ref_columns = [table.dcim_devicetype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_device_types_configcontext_id_55632923" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_device_types_devicetype_id_b8788c2d" {
    columns = [column.devicetype_id]
  }
  unique "extras_configcontext_dev_configcontext_id_devicet_a0aaba6f_uniq" {
    columns = [column.configcontext_id, column.devicetype_id]
  }
}
table "extras_configcontext_locations" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "location_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_cc629ec1_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_location_id_9e19eac9_fk_dcim_loca" {
    columns     = [column.location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_locations_configcontext_id_cc629ec1" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_locations_location_id_9e19eac9" {
    columns = [column.location_id]
  }
  unique "extras_configcontext_loc_configcontext_id_locatio_15d9b342_uniq" {
    columns = [column.configcontext_id, column.location_id]
  }
}
table "extras_configcontext_platforms" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "platform_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_2a516699_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_platform_id_3fdfedc0_fk_dcim_plat" {
    columns     = [column.platform_id]
    ref_columns = [table.dcim_platform.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_platforms_configcontext_id_2a516699" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_platforms_platform_id_3fdfedc0" {
    columns = [column.platform_id]
  }
  unique "extras_configcontext_pla_configcontext_id_platfor_3c67c104_uniq" {
    columns = [column.configcontext_id, column.platform_id]
  }
}
table "extras_configcontext_regions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "region_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_73003dbc_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_region_id_35c6ba9d_fk_dcim_regi" {
    columns     = [column.region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_regions_configcontext_id_73003dbc" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_regions_region_id_35c6ba9d" {
    columns = [column.region_id]
  }
  unique "extras_configcontext_reg_configcontext_id_region__d4a1d77f_uniq" {
    columns = [column.configcontext_id, column.region_id]
  }
}
table "extras_configcontext_roles" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "devicerole_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_59b67386_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_devicerole_id_d3a84813_fk_dcim_devi" {
    columns     = [column.devicerole_id]
    ref_columns = [table.dcim_devicerole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_roles_configcontext_id_59b67386" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_roles_devicerole_id_d3a84813" {
    columns = [column.devicerole_id]
  }
  unique "extras_configcontext_rol_configcontext_id_devicer_4d8dbb50_uniq" {
    columns = [column.configcontext_id, column.devicerole_id]
  }
}
table "extras_configcontext_site_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "sitegroup_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_2e0f43cb_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_sitegroup_id_3287c9e7_fk_dcim_site" {
    columns     = [column.sitegroup_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_site_groups_configcontext_id_2e0f43cb" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_site_groups_sitegroup_id_3287c9e7" {
    columns = [column.sitegroup_id]
  }
  unique "extras_configcontext_sit_configcontext_id_sitegro_4caa52ec_uniq" {
    columns = [column.configcontext_id, column.sitegroup_id]
  }
}
table "extras_configcontext_sites" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "site_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_8c54feb9_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_sites_site_id_cbb76c96_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_sites_configcontext_id_8c54feb9" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_sites_site_id_cbb76c96" {
    columns = [column.site_id]
  }
  unique "extras_configcontext_sit_configcontext_id_site_id_a4fe5f4f_uniq" {
    columns = [column.configcontext_id, column.site_id]
  }
}
table "extras_configcontext_tags" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "tag_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_64a392b1_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_tags_tag_id_129a5d87_fk_extras_tag_id" {
    columns     = [column.tag_id]
    ref_columns = [table.extras_tag.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_tags_configcontext_id_64a392b1" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_tags_tag_id_129a5d87" {
    columns = [column.tag_id]
  }
  unique "extras_configcontext_tags_configcontext_id_tag_id_f6c53016_uniq" {
    columns = [column.configcontext_id, column.tag_id]
  }
}
table "extras_configcontext_tenant_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "tenantgroup_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_92f68345_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_tenantgroup_id_0909688d_fk_tenancy_t" {
    columns     = [column.tenantgroup_id]
    ref_columns = [table.tenancy_tenantgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_tenant_groups_configcontext_id_92f68345" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_tenant_groups_tenantgroup_id_0909688d" {
    columns = [column.tenantgroup_id]
  }
  unique "extras_configcontext_ten_configcontext_id_tenantg_d6afc6f5_uniq" {
    columns = [column.configcontext_id, column.tenantgroup_id]
  }
}
table "extras_configcontext_tenants" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "configcontext_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_configcontext_id_b53552a6_fk_extras_co" {
    columns     = [column.configcontext_id]
    ref_columns = [table.extras_configcontext.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_tenant_id_8d0aa28e_fk_tenancy_t" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontext_tenants_configcontext_id_b53552a6" {
    columns = [column.configcontext_id]
  }
  index "extras_configcontext_tenants_tenant_id_8d0aa28e" {
    columns = [column.tenant_id]
  }
  unique "extras_configcontext_ten_configcontext_id_tenant__aefb257d_uniq" {
    columns = [column.configcontext_id, column.tenant_id]
  }
}
table "extras_configcontextprofile" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "data_path" {
    null = false
    type = character_varying(1000)
  }
  column "auto_sync_enabled" {
    null = false
    type = boolean
  }
  column "data_synced" {
    null = true
    type = timestamptz
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "schema" {
    null = true
    type = jsonb
  }
  column "data_file_id" {
    null = true
    type = bigint
  }
  column "data_source_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configcontext_data_file_id_e0caf376_fk_core_data" {
    columns     = [column.data_file_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontext_data_source_id_b88dd849_fk_core_data" {
    columns     = [column.data_source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configcontextprofile_owner_id_6b1a975e_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configcontextprofile_data_file_id_e0caf376" {
    columns = [column.data_file_id]
  }
  index "extras_configcontextprofile_data_source_id_b88dd849" {
    columns = [column.data_source_id]
  }
  index "extras_configcontextprofile_name_070de83b_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_configcontextprofile_owner_id_6b1a975e" {
    columns = [column.owner_id]
  }
  unique "extras_configcontextprofile_name_key" {
    columns = [column.name]
  }
}
table "extras_configtemplate" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "data_path" {
    null = false
    type = character_varying(1000)
  }
  column "data_synced" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "template_code" {
    null = false
    type = text
  }
  column "environment_params" {
    null = true
    type = jsonb
  }
  column "data_file_id" {
    null = true
    type = bigint
  }
  column "data_source_id" {
    null = true
    type = bigint
  }
  column "auto_sync_enabled" {
    null = false
    type = boolean
  }
  column "as_attachment" {
    null = false
    type = boolean
  }
  column "file_extension" {
    null = false
    type = character_varying(15)
  }
  column "file_name" {
    null = false
    type = character_varying(200)
  }
  column "mime_type" {
    null = false
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_configtemplat_data_source_id_f9d26d5d_fk_core_data" {
    columns     = [column.data_source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configtemplate_data_file_id_20c7cff4_fk_core_datafile_id" {
    columns     = [column.data_file_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_configtemplate_owner_id_0925c336_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_configtemplate_data_file_id_20c7cff4" {
    columns = [column.data_file_id]
  }
  index "extras_configtemplate_data_source_id_f9d26d5d" {
    columns = [column.data_source_id]
  }
  index "extras_configtemplate_owner_id_0925c336" {
    columns = [column.owner_id]
  }
}
table "extras_customfield" {
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
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(50)
  }
  column "label" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "required" {
    null = false
    type = boolean
  }
  column "filter_logic" {
    null = false
    type = character_varying(50)
  }
  column "default" {
    null = true
    type = jsonb
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "validation_minimum" {
    null = true
    type = numeric(16,4)
  }
  column "validation_maximum" {
    null = true
    type = numeric(16,4)
  }
  column "validation_regex" {
    null = false
    type = character_varying(500)
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "related_object_type_id" {
    null = true
    type = integer
  }
  column "group_name" {
    null = false
    type = character_varying(50)
  }
  column "search_weight" {
    null = false
    type = smallint
  }
  column "is_cloneable" {
    null = false
    type = boolean
  }
  column "choice_set_id" {
    null = true
    type = bigint
  }
  column "ui_editable" {
    null = false
    type = character_varying(50)
  }
  column "ui_visible" {
    null = false
    type = character_varying(50)
  }
  column "comments" {
    null = false
    type = text
  }
  column "unique" {
    null = false
    type = boolean
  }
  column "related_object_filter" {
    null = true
    type = jsonb
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_customfield_choice_set_id_5590efc2_fk_extras_cu" {
    columns     = [column.choice_set_id]
    ref_columns = [table.extras_customfieldchoiceset.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_customfield_owner_id_558f69a3_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_customfield_related_object_type__fa9aa45b_fk_django_co" {
    columns     = [column.related_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_customfield_choice_set_id_5590efc2" {
    columns = [column.choice_set_id]
  }
  index "extras_customfield_name_2fe72707_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_customfield_object_type_id_489f2239" {
    columns = [column.related_object_type_id]
  }
  index "extras_customfield_owner_id_558f69a3" {
    columns = [column.owner_id]
  }
  check "extras_customfield_search_weight_check" {
    expr = "(search_weight >= 0)"
  }
  check "extras_customfield_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "extras_customfield_name_key" {
    columns = [column.name]
  }
}
table "extras_customfield_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "customfield_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_customfield_c_customfield_id_3842aaf3_fk_extras_cu" {
    columns     = [column.customfield_id]
    ref_columns = [table.extras_customfield.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_customfield_o_contenttype_id_d9167062_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_customfield_content_types_contenttype_id_2997ba90" {
    columns = [column.contenttype_id]
  }
  index "extras_customfield_content_types_customfield_id_3842aaf3" {
    columns = [column.customfield_id]
  }
  unique "extras_customfield_conte_customfield_id_contentty_51136c2b_uniq" {
    columns = [column.customfield_id, column.contenttype_id]
  }
}
table "extras_customfieldchoiceset" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "base_choices" {
    null = true
    type = character_varying(50)
  }
  column "extra_choices" {
    null = true
    type = sql("character varying(100)[]")
  }
  column "order_alphabetically" {
    null = false
    type = boolean
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_customfieldchoiceset_owner_id_02d6fc4d_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_customfieldchoiceset_name_963e63ea_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_customfieldchoiceset_owner_id_02d6fc4d" {
    columns = [column.owner_id]
  }
  unique "extras_customfieldchoiceset_name_key" {
    columns = [column.name]
  }
}
table "extras_customlink" {
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
    type = character_varying(100)
  }
  column "link_text" {
    null = false
    type = text
  }
  column "link_url" {
    null = false
    type = text
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "group_name" {
    null = false
    type = character_varying(50)
  }
  column "button_class" {
    null = false
    type = character_varying(30)
  }
  column "new_window" {
    null = false
    type = boolean
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_customlink_owner_id_b4449049_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_customlink_name_daed2d18_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_customlink_owner_id_b4449049" {
    columns = [column.owner_id]
  }
  check "extras_customlink_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "extras_customlink_name_key" {
    columns = [column.name]
  }
}
table "extras_customlink_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "customlink_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_customlink_co_customlink_id_229ba2bc_fk_extras_cu" {
    columns     = [column.customlink_id]
    ref_columns = [table.extras_customlink.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_customlink_ob_contenttype_id_600977f4_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_customlink_content_types_contenttype_id_df5f34c2" {
    columns = [column.contenttype_id]
  }
  index "extras_customlink_content_types_customlink_id_229ba2bc" {
    columns = [column.customlink_id]
  }
  unique "extras_customlink_conten_customlink_id_contenttyp_518ef1b8_uniq" {
    columns = [column.customlink_id, column.contenttype_id]
  }
}
table "extras_dashboard" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "layout" {
    null = false
    type = jsonb
  }
  column "config" {
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
  foreign_key "extras_dashboard_user_id_f1e1278b_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "extras_dashboard_user_id_key" {
    columns = [column.user_id]
  }
}
table "extras_eventrule" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(150)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "conditions" {
    null = true
    type = jsonb
  }
  column "action_type" {
    null = false
    type = character_varying(30)
  }
  column "action_object_id" {
    null = true
    type = bigint
  }
  column "action_data" {
    null = true
    type = jsonb
  }
  column "comments" {
    null = false
    type = text
  }
  column "action_object_type_id" {
    null = false
    type = integer
  }
  column "event_types" {
    null = false
    type = sql("character varying(50)[]")
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_eventrule_action_object_type_i_1fe8a82e_fk_django_co" {
    columns     = [column.action_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_eventrule_owner_id_a4c56a12_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_even_action__d9e2af_idx" {
    columns = [column.action_object_type_id, column.action_object_id]
  }
  index "extras_eventrule_action_object_type_id_1fe8a82e" {
    columns = [column.action_object_type_id]
  }
  index "extras_eventrule_name_899453c6_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_eventrule_owner_id_a4c56a12" {
    columns = [column.owner_id]
  }
  check "extras_eventrule_action_object_id_check" {
    expr = "(action_object_id >= 0)"
  }
  unique "extras_eventrule_name_key" {
    columns = [column.name]
  }
}
table "extras_eventrule_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "eventrule_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_eventrule_con_eventrule_id_c177fa54_fk_extras_ev" {
    columns     = [column.eventrule_id]
    ref_columns = [table.extras_eventrule.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_eventrule_obj_contenttype_id_1ec4bbcc_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_eventrule_content_types_contenttype_id_a704fd34" {
    columns = [column.contenttype_id]
  }
  index "extras_eventrule_content_types_eventrule_id_c177fa54" {
    columns = [column.eventrule_id]
  }
  unique "extras_eventrule_content_eventrule_id_contenttype_4da93239_uniq" {
    columns = [column.eventrule_id, column.contenttype_id]
  }
}
table "extras_exporttemplate" {
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
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "template_code" {
    null = false
    type = text
  }
  column "mime_type" {
    null = false
    type = character_varying(50)
  }
  column "file_extension" {
    null = false
    type = character_varying(15)
  }
  column "as_attachment" {
    null = false
    type = boolean
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "data_file_id" {
    null = true
    type = bigint
  }
  column "data_path" {
    null = false
    type = character_varying(1000)
  }
  column "data_source_id" {
    null = true
    type = bigint
  }
  column "auto_sync_enabled" {
    null = false
    type = boolean
  }
  column "data_synced" {
    null = true
    type = timestamptz
  }
  column "file_name" {
    null = false
    type = character_varying(200)
  }
  column "environment_params" {
    null = true
    type = jsonb
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_exporttemplat_data_source_id_d61d0feb_fk_core_data" {
    columns     = [column.data_source_id]
    ref_columns = [table.core_datasource.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_exporttemplate_data_file_id_40a91ef8_fk_core_datafile_id" {
    columns     = [column.data_file_id]
    ref_columns = [table.core_datafile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_exporttemplate_owner_id_a690b184_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_exporttemplate_data_file_id_40a91ef8" {
    columns = [column.data_file_id]
  }
  index "extras_exporttemplate_data_source_id_d61d0feb" {
    columns = [column.data_source_id]
  }
  index "extras_exporttemplate_owner_id_a690b184" {
    columns = [column.owner_id]
  }
}
table "extras_exporttemplate_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "exporttemplate_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_exporttemplat_contenttype_id_0f034708_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_exporttemplat_exporttemplate_id_7645f081_fk_extras_ex" {
    columns     = [column.exporttemplate_id]
    ref_columns = [table.extras_exporttemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_exporttemplate_content_types_contenttype_id_d80a5164" {
    columns = [column.contenttype_id]
  }
  index "extras_exporttemplate_content_types_exporttemplate_id_7645f081" {
    columns = [column.exporttemplate_id]
  }
  unique "extras_exporttemplate_co_exporttemplate_id_conten_b4645653_uniq" {
    columns = [column.exporttemplate_id, column.contenttype_id]
  }
}
table "extras_imageattachment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "image" {
    null = false
    type = character_varying(100)
  }
  column "image_height" {
    null = false
    type = smallint
  }
  column "image_width" {
    null = false
    type = smallint
  }
  column "name" {
    null = false
    type = character_varying(50)
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_imageattachme_object_type_id_a9400c38_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_imag_object__96bebc_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "extras_imageattachment_content_type_id_90e0643d" {
    columns = [column.object_type_id]
  }
  check "extras_imageattachment_image_height_check" {
    expr = "(image_height >= 0)"
  }
  check "extras_imageattachment_image_width_check" {
    expr = "(image_width >= 0)"
  }
  check "extras_imageattachment_object_id_check" {
    expr = "(object_id >= 0)"
  }
}
table "extras_journalentry" {
  schema = schema.public
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "assigned_object_id" {
    null = false
    type = bigint
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "kind" {
    null = false
    type = character_varying(30)
  }
  column "comments" {
    null = false
    type = text
  }
  column "assigned_object_type_id" {
    null = false
    type = integer
  }
  column "created_by_id" {
    null = true
    type = bigint
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_journalentry_assigned_object_type_1bba9f68_fk_django_co" {
    columns     = [column.assigned_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_journalentry_created_by_id_8d4e4329_fk_auth_user_id" {
    columns     = [column.created_by_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_jour_assigne_76510f_idx" {
    columns = [column.assigned_object_type_id, column.assigned_object_id]
  }
  index "extras_journalentry_assigned_object_type_id_1bba9f68" {
    columns = [column.assigned_object_type_id]
  }
  index "extras_journalentry_created_by_id_8d4e4329" {
    columns = [column.created_by_id]
  }
  check "extras_journalentry_assigned_object_id_check" {
    expr = "(assigned_object_id >= 0)"
  }
}
table "extras_notification" {
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
  column "read" {
    null = true
    type = timestamptz
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "event_type" {
    null = false
    type = character_varying(50)
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "object_repr" {
    null = false
    type = character_varying(200)
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_notification_object_type_id_2efeb525_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_notification_user_id_4d8c96f5_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_noti_object__be74d5_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "extras_notification_object_type_id_2efeb525" {
    columns = [column.object_type_id]
  }
  index "extras_notification_user_id_4d8c96f5" {
    columns = [column.user_id]
  }
  check "extras_notification_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "extras_notification_unique_per_object_and_user" {
    columns = [column.object_type_id, column.object_id, column.user_id]
  }
}
table "extras_notificationgroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  index "extras_notificationgroup_name_70b0a3f9_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  unique "extras_notificationgroup_name_key" {
    columns = [column.name]
  }
}
table "extras_notificationgroup_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "notificationgroup_id" {
    null = false
    type = bigint
  }
  column "group_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_notificationg_group_id_af4b7b6c_fk_users_gro" {
    columns     = [column.group_id]
    ref_columns = [table.users_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_notificationg_notificationgroup_id_a41469f7_fk_extras_no" {
    columns     = [column.notificationgroup_id]
    ref_columns = [table.extras_notificationgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_notificationgroup_groups_group_id_af4b7b6c" {
    columns = [column.group_id]
  }
  index "extras_notificationgroup_groups_notificationgroup_id_a41469f7" {
    columns = [column.notificationgroup_id]
  }
  unique "extras_notificationgroup_notificationgroup_id_gro_46702115_uniq" {
    columns = [column.notificationgroup_id, column.group_id]
  }
}
table "extras_notificationgroup_users" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "notificationgroup_id" {
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
  foreign_key "extras_notificationg_notificationgroup_id_0a8ec85c_fk_extras_no" {
    columns     = [column.notificationgroup_id]
    ref_columns = [table.extras_notificationgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_notificationg_user_id_2c30da19_fk_users_use" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_notificationgroup_users_notificationgroup_id_0a8ec85c" {
    columns = [column.notificationgroup_id]
  }
  index "extras_notificationgroup_users_user_id_2c30da19" {
    columns = [column.user_id]
  }
  unique "extras_notificationgroup_notificationgroup_id_use_9a79b7f8_uniq" {
    columns = [column.notificationgroup_id, column.user_id]
  }
}
table "extras_savedfilter" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "shared" {
    null = false
    type = boolean
  }
  column "parameters" {
    null = false
    type = jsonb
  }
  column "user_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_savedfilter_owner_id_e022149a_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_savedfilter_user_id_10502e81_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_savedfilter_name_8a4bbd09_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_savedfilter_owner_id_e022149a" {
    columns = [column.owner_id]
  }
  index "extras_savedfilter_slug_4f93a959_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "extras_savedfilter_user_id_10502e81" {
    columns = [column.user_id]
  }
  check "extras_savedfilter_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "extras_savedfilter_name_key" {
    columns = [column.name]
  }
  unique "extras_savedfilter_slug_key" {
    columns = [column.slug]
  }
}
table "extras_savedfilter_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "savedfilter_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_savedfilter_c_savedfilter_id_1631b88b_fk_extras_sa" {
    columns     = [column.savedfilter_id]
    ref_columns = [table.extras_savedfilter.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_savedfilter_o_contenttype_id_bbf68799_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_savedfilter_content_types_contenttype_id_929cea22" {
    columns = [column.contenttype_id]
  }
  index "extras_savedfilter_content_types_savedfilter_id_1631b88b" {
    columns = [column.savedfilter_id]
  }
  unique "extras_savedfilter_conte_savedfilter_id_contentty_133ba781_uniq" {
    columns = [column.savedfilter_id, column.contenttype_id]
  }
}
table "extras_script" {
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
    type = character_varying(79)
  }
  column "module_id" {
    null = false
    type = bigint
  }
  column "is_executable" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_script_module_id_af9cffaa_fk_core_managedfile_id" {
    columns     = [column.module_id]
    ref_columns = [table.core_managedfile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_script_module_id_af9cffaa" {
    columns = [column.module_id]
  }
  unique "extras_script_unique_name_module" {
    columns = [column.name, column.module_id]
  }
}
table "extras_subscription" {
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
  column "object_id" {
    null = false
    type = bigint
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_subscription_object_type_id_e53297d2_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_subscription_user_id_37472a14_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_subs_object__37ef68_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "extras_subscription_object_type_id_e53297d2" {
    columns = [column.object_type_id]
  }
  index "extras_subscription_user_id_37472a14" {
    columns = [column.user_id]
  }
  check "extras_subscription_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "extras_subscription_unique_per_object_and_user" {
    columns = [column.object_type_id, column.object_id, column.user_id]
  }
}
table "extras_tableconfig" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "table" {
    null = false
    type = character_varying(100)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "shared" {
    null = false
    type = boolean
  }
  column "columns" {
    null = false
    type = sql("character varying(100)[]")
  }
  column "ordering" {
    null = true
    type = sql("character varying(100)[]")
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "user_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_tableconfig_object_type_id_e43ad6ad_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_tableconfig_user_id_0b525dff_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_tableconfig_object_type_id_e43ad6ad" {
    columns = [column.object_type_id]
  }
  index "extras_tableconfig_user_id_0b525dff" {
    columns = [column.user_id]
  }
  check "extras_tableconfig_weight_check" {
    expr = "(weight >= 0)"
  }
}
table "extras_tag" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "color" {
    null = false
    type = character_varying(6)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_tag_owner_id_ebb991ad_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_tag_name_9550b3d9_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_tag_owner_id_ebb991ad" {
    columns = [column.owner_id]
  }
  index "extras_tag_slug_aaa5b7e9_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "extras_tag_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "extras_tag_name_key" {
    columns = [column.name]
  }
  unique "extras_tag_slug_key" {
    columns = [column.slug]
  }
}
table "extras_tag_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "tag_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_tag_object_ty_contenttype_id_c1b220c3_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_tag_object_types_tag_id_2e1aab29_fk_extras_tag_id" {
    columns     = [column.tag_id]
    ref_columns = [table.extras_tag.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_tag_object_types_contenttype_id_c1b220c3" {
    columns = [column.contenttype_id]
  }
  index "extras_tag_object_types_tag_id_2e1aab29" {
    columns = [column.tag_id]
  }
  unique "extras_tag_object_types_tag_id_contenttype_id_2ff9910c_uniq" {
    columns = [column.tag_id, column.contenttype_id]
  }
}
table "extras_taggeditem" {
  schema = schema.public
  column "object_id" {
    null = false
    type = integer
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "content_type_id" {
    null = false
    type = integer
  }
  column "tag_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_taggeditem_content_type_id_ba5562ed_fk_django_co" {
    columns     = [column.content_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "extras_taggeditem_tag_id_d48af7c7_fk_extras_tag_id" {
    columns     = [column.tag_id]
    ref_columns = [table.extras_tag.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_tagg_content_717743_idx" {
    columns = [column.content_type_id, column.object_id]
  }
  index "extras_taggeditem_content_type_id_ba5562ed" {
    columns = [column.content_type_id]
  }
  index "extras_taggeditem_object_id_31b2aa77" {
    columns = [column.object_id]
  }
  index "extras_taggeditem_tag_id_d48af7c7" {
    columns = [column.tag_id]
  }
}
table "extras_webhook" {
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
    type = character_varying(150)
  }
  column "payload_url" {
    null = false
    type = character_varying(500)
  }
  column "http_method" {
    null = false
    type = character_varying(30)
  }
  column "http_content_type" {
    null = false
    type = character_varying(100)
  }
  column "additional_headers" {
    null = false
    type = text
  }
  column "body_template" {
    null = false
    type = text
  }
  column "secret" {
    null = false
    type = character_varying(255)
  }
  column "ssl_verification" {
    null = false
    type = boolean
  }
  column "ca_file_path" {
    null = true
    type = character_varying(4096)
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "extras_webhook_owner_id_bcf756a8_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "extras_webhook_name_82cf60b5_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "extras_webhook_owner_id_bcf756a8" {
    columns = [column.owner_id]
  }
  unique "extras_webhook_name_key" {
    columns = [column.name]
  }
}
table "ipam_aggregate" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "prefix" {
    null = false
    type = cidr
  }
  column "date_added" {
    null = true
    type = date
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "rir_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_aggregate_owner_id_fdaa939f_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_aggregate_rir_id_ef7a27bd_fk_ipam_rir_id" {
    columns     = [column.rir_id]
    ref_columns = [table.ipam_rir.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_aggregate_tenant_id_637dd1a1_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_aggregate_owner_id_fdaa939f" {
    columns = [column.owner_id]
  }
  index "ipam_aggregate_rir_id_ef7a27bd" {
    columns = [column.rir_id]
  }
  index "ipam_aggregate_tenant_id_637dd1a1" {
    columns = [column.tenant_id]
  }
}
table "ipam_asn" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "asn" {
    null = false
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "rir_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_asn_owner_id_2ab253b3_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_asn_rir_id_f5ad3cff_fk_ipam_rir_id" {
    columns     = [column.rir_id]
    ref_columns = [table.ipam_rir.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_asn_tenant_id_07e8188e_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_asn_owner_id_2ab253b3" {
    columns = [column.owner_id]
  }
  index "ipam_asn_rir_id_f5ad3cff" {
    columns = [column.rir_id]
  }
  index "ipam_asn_tenant_id_07e8188e" {
    columns = [column.tenant_id]
  }
  unique "ipam_asn_asn_key" {
    columns = [column.asn]
  }
}
table "ipam_asnrange" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "start" {
    null = false
    type = bigint
  }
  column "end" {
    null = false
    type = bigint
  }
  column "rir_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_asnrange_owner_id_a943e984_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_asnrange_rir_id_c9c31183_fk_ipam_rir_id" {
    columns     = [column.rir_id]
    ref_columns = [table.ipam_rir.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_asnrange_tenant_id_ed8f80b7_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_asnrange_name_c7585e73_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_asnrange_owner_id_a943e984" {
    columns = [column.owner_id]
  }
  index "ipam_asnrange_rir_id_c9c31183" {
    columns = [column.rir_id]
  }
  index "ipam_asnrange_slug_c8a7d8a1_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_asnrange_tenant_id_ed8f80b7" {
    columns = [column.tenant_id]
  }
  unique "ipam_asnrange_name_key" {
    columns = [column.name]
  }
  unique "ipam_asnrange_slug_key" {
    columns = [column.slug]
  }
}
table "ipam_fhrpgroup" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "group_id" {
    null = false
    type = smallint
  }
  column "protocol" {
    null = false
    type = character_varying(50)
  }
  column "auth_type" {
    null = true
    type = character_varying(50)
  }
  column "auth_key" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_fhrpgroup_owner_id_f5209119_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_fhrpgroup_owner_id_f5209119" {
    columns = [column.owner_id]
  }
  check "ipam_fhrpgroup_group_id_check" {
    expr = "(group_id >= 0)"
  }
}
table "ipam_fhrpgroupassignment" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "interface_id" {
    null = false
    type = bigint
  }
  column "priority" {
    null = false
    type = smallint
  }
  column "group_id" {
    null = false
    type = bigint
  }
  column "interface_type_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_fhrpgroupassign_interface_type_id_f3bcb487_fk_django_co" {
    columns     = [column.interface_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_fhrpgroupassignment_group_id_19f15ca4_fk_ipam_fhrpgroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.ipam_fhrpgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_fhrpgr_interfa_2acc3f_idx" {
    columns = [column.interface_type_id, column.interface_id]
  }
  index "ipam_fhrpgroupassignment_group_id_19f15ca4" {
    columns = [column.group_id]
  }
  index "ipam_fhrpgroupassignment_interface_type_id_f3bcb487" {
    columns = [column.interface_type_id]
  }
  check "ipam_fhrpgroupassignment_interface_id_check" {
    expr = "(interface_id >= 0)"
  }
  check "ipam_fhrpgroupassignment_priority_check" {
    expr = "(priority >= 0)"
  }
  unique "ipam_fhrpgroupassignment_unique_interface_group" {
    columns = [column.interface_type_id, column.interface_id, column.group_id]
  }
}
table "ipam_ipaddress" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "address" {
    null = false
    type = inet
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "role" {
    null = true
    type = character_varying(50)
  }
  column "assigned_object_id" {
    null = true
    type = bigint
  }
  column "dns_name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "assigned_object_type_id" {
    null = true
    type = integer
  }
  column "nat_inside_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "vrf_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_ipaddress_assigned_object_type_02354370_fk_django_co" {
    columns     = [column.assigned_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_ipaddress_nat_inside_id_a45fb7c5_fk_ipam_ipaddress_id" {
    columns     = [column.nat_inside_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_ipaddress_owner_id_47736b63_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_ipaddress_tenant_id_ac55acfd_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_ipaddress_vrf_id_51fcc59b_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_ipaddr_assigne_890ab8_idx" {
    columns = [column.assigned_object_type_id, column.assigned_object_id]
  }
  index "ipam_ipaddress_assigned_object_type_id_02354370" {
    columns = [column.assigned_object_type_id]
  }
  index "ipam_ipaddress_host" {
    on {
      expr = "((host(address))::inet)"
    }
  }
  index "ipam_ipaddress_nat_inside_id_a45fb7c5" {
    columns = [column.nat_inside_id]
  }
  index "ipam_ipaddress_owner_id_47736b63" {
    columns = [column.owner_id]
  }
  index "ipam_ipaddress_tenant_id_ac55acfd" {
    columns = [column.tenant_id]
  }
  index "ipam_ipaddress_vrf_id_51fcc59b" {
    columns = [column.vrf_id]
  }
  check "ipam_ipaddress_assigned_object_id_check" {
    expr = "(assigned_object_id >= 0)"
  }
}
table "ipam_iprange" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "start_address" {
    null = false
    type = inet
  }
  column "end_address" {
    null = false
    type = inet
  }
  column "size" {
    null = false
    type = integer
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "vrf_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "mark_utilized" {
    null = false
    type = boolean
  }
  column "mark_populated" {
    null = false
    type = boolean
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_iprange_owner_id_b327afb7_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_iprange_role_id_2782e864_fk_ipam_role_id" {
    columns     = [column.role_id]
    ref_columns = [table.ipam_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_iprange_tenant_id_856027ea_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_iprange_vrf_id_613e9dd2_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_iprange_owner_id_b327afb7" {
    columns = [column.owner_id]
  }
  index "ipam_iprange_role_id_2782e864" {
    columns = [column.role_id]
  }
  index "ipam_iprange_tenant_id_856027ea" {
    columns = [column.tenant_id]
  }
  index "ipam_iprange_vrf_id_613e9dd2" {
    columns = [column.vrf_id]
  }
  check "ipam_iprange_size_check" {
    expr = "(size >= 0)"
  }
}
table "ipam_prefix" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "prefix" {
    null = false
    type = cidr
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "is_pool" {
    null = false
    type = boolean
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "vlan_id" {
    null = true
    type = bigint
  }
  column "vrf_id" {
    null = true
    type = bigint
  }
  column "_children" {
    null = false
    type = bigint
  }
  column "_depth" {
    null = false
    type = smallint
  }
  column "mark_utilized" {
    null = false
    type = boolean
  }
  column "comments" {
    null = false
    type = text
  }
  column "scope_id" {
    null = true
    type = bigint
  }
  column "scope_type_id" {
    null = true
    type = integer
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_region_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "_site_group_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_prefix__location_id_f5925c42_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix__region_id_54aedc72_fk_dcim_region_id" {
    columns     = [column._region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix__site_group_id_8277120b_fk_dcim_sitegroup_id" {
    columns     = [column._site_group_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix__site_id_b479fb05_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_owner_id_12d43bc8_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_role_id_0a98d415_fk_ipam_role_id" {
    columns     = [column.role_id]
    ref_columns = [table.ipam_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_scope_type_id_413319e2_fk_django_content_type_id" {
    columns     = [column.scope_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_tenant_id_7ba1fcc4_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_vlan_id_1db91bff_fk_ipam_vlan_id" {
    columns     = [column.vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_prefix_vrf_id_34f78ed0_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_prefix__location_id_f5925c42" {
    columns = [column._location_id]
  }
  index "ipam_prefix__region_id_54aedc72" {
    columns = [column._region_id]
  }
  index "ipam_prefix__site_group_id_8277120b" {
    columns = [column._site_group_id]
  }
  index "ipam_prefix__site_id_b479fb05" {
    columns = [column._site_id]
  }
  index "ipam_prefix_gist_idx" {
    type = GIST
    on {
      column = column.prefix
      ops    = inet_ops
    }
  }
  index "ipam_prefix_owner_id_12d43bc8" {
    columns = [column.owner_id]
  }
  index "ipam_prefix_role_id_0a98d415" {
    columns = [column.role_id]
  }
  index "ipam_prefix_scope_t_fe84a6_idx" {
    columns = [column.scope_type_id, column.scope_id]
  }
  index "ipam_prefix_scope_type_id_413319e2" {
    columns = [column.scope_type_id]
  }
  index "ipam_prefix_tenant_id_7ba1fcc4" {
    columns = [column.tenant_id]
  }
  index "ipam_prefix_vlan_id_1db91bff" {
    columns = [column.vlan_id]
  }
  index "ipam_prefix_vrf_id_34f78ed0" {
    columns = [column.vrf_id]
  }
  check "ipam_prefix__children_check" {
    expr = "(_children >= 0)"
  }
  check "ipam_prefix__depth_check" {
    expr = "(_depth >= 0)"
  }
  check "ipam_prefix_scope_id_check" {
    expr = "(scope_id >= 0)"
  }
}
table "ipam_rir" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "is_private" {
    null = false
    type = boolean
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_rir_owner_id_172cc053_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_rir_name_64a71982_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_rir_owner_id_172cc053" {
    columns = [column.owner_id]
  }
  index "ipam_rir_slug_ff1a369a_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "ipam_rir_name_key" {
    columns = [column.name]
  }
  unique "ipam_rir_slug_key" {
    columns = [column.slug]
  }
}
table "ipam_role" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "weight" {
    null = false
    type = smallint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_role_owner_id_b42367ab_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_role_name_13784849_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_role_owner_id_b42367ab" {
    columns = [column.owner_id]
  }
  index "ipam_role_slug_309ca14c_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  check "ipam_role_weight_check" {
    expr = "(weight >= 0)"
  }
  unique "ipam_role_name_key" {
    columns = [column.name]
  }
  unique "ipam_role_slug_key" {
    columns = [column.slug]
  }
}
table "ipam_routetarget" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(21)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_routetarget_owner_id_e968953a_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_routetarget_tenant_id_5a0b35e8_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_routetarget_name_212be79f_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_routetarget_owner_id_e968953a" {
    columns = [column.owner_id]
  }
  index "ipam_routetarget_tenant_id_5a0b35e8" {
    columns = [column.tenant_id]
  }
  unique "ipam_routetarget_name_key" {
    columns = [column.name]
  }
}
table "ipam_service" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "protocol" {
    null = false
    type = character_varying(50)
  }
  column "ports" {
    null = false
    type = sql("integer[]")
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "parent_object_id" {
    null = false
    type = bigint
  }
  column "parent_object_type_id" {
    null = false
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_service_owner_id_ab1c827a_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_service_parent_object_type_i_8e76bfb3_fk_django_co" {
    columns     = [column.parent_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_servic_parent__563d2b_idx" {
    columns = [column.parent_object_type_id, column.parent_object_id]
  }
  index "ipam_service_owner_id_ab1c827a" {
    columns = [column.owner_id]
  }
  index "ipam_service_parent_object_type_id_8e76bfb3" {
    columns = [column.parent_object_type_id]
  }
  check "ipam_service_parent_object_id_check" {
    expr = "(parent_object_id >= 0)"
  }
}
table "ipam_service_ipaddresses" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "service_id" {
    null = false
    type = bigint
  }
  column "ipaddress_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_service_ipaddre_ipaddress_id_b4138c6d_fk_ipam_ipad" {
    columns     = [column.ipaddress_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_service_ipaddresses_service_id_ae26b9ab_fk_ipam_service_id" {
    columns     = [column.service_id]
    ref_columns = [table.ipam_service.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_service_ipaddresses_ipaddress_id_b4138c6d" {
    columns = [column.ipaddress_id]
  }
  index "ipam_service_ipaddresses_service_id_ae26b9ab" {
    columns = [column.service_id]
  }
  unique "ipam_service_ipaddresses_service_id_ipaddress_id_d019a805_uniq" {
    columns = [column.service_id, column.ipaddress_id]
  }
}
table "ipam_servicetemplate" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "protocol" {
    null = false
    type = character_varying(50)
  }
  column "ports" {
    null = false
    type = sql("integer[]")
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_servicetemplate_owner_id_bd152acb_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_servicetemplate_name_1a2f3410_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_servicetemplate_owner_id_bd152acb" {
    columns = [column.owner_id]
  }
  unique "ipam_servicetemplate_name_key" {
    columns = [column.name]
  }
}
table "ipam_vlan" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "vid" {
    null = false
    type = smallint
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "qinq_role" {
    null = true
    type = character_varying(50)
  }
  column "qinq_svlan_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vlan_group_id_88cbfa62_fk_ipam_vlangroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.ipam_vlangroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlan_owner_id_ead15d2b_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlan_qinq_svlan_id_acbd7a5d_fk_ipam_vlan_id" {
    columns     = [column.qinq_svlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlan_role_id_f5015962_fk_ipam_role_id" {
    columns     = [column.role_id]
    ref_columns = [table.ipam_role.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlan_site_id_a59334e3_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlan_tenant_id_71a8290d_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vlan_group_id_88cbfa62" {
    columns = [column.group_id]
  }
  index "ipam_vlan_owner_id_ead15d2b" {
    columns = [column.owner_id]
  }
  index "ipam_vlan_qinq_svlan_id_acbd7a5d" {
    columns = [column.qinq_svlan_id]
  }
  index "ipam_vlan_role_id_f5015962" {
    columns = [column.role_id]
  }
  index "ipam_vlan_site_id_a59334e3" {
    columns = [column.site_id]
  }
  index "ipam_vlan_tenant_id_71a8290d" {
    columns = [column.tenant_id]
  }
  check "ipam_vlan_vid_check" {
    expr = "(vid >= 0)"
  }
  unique "ipam_vlan_unique_group_name" {
    columns = [column.group_id, column.name]
  }
  unique "ipam_vlan_unique_group_vid" {
    columns = [column.group_id, column.vid]
  }
  unique "ipam_vlan_unique_qinq_svlan_name" {
    columns = [column.qinq_svlan_id, column.name]
  }
  unique "ipam_vlan_unique_qinq_svlan_vid" {
    columns = [column.qinq_svlan_id, column.vid]
  }
}
table "ipam_vlangroup" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "scope_id" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "scope_type_id" {
    null = true
    type = integer
  }
  column "vid_ranges" {
    null = false
    type = sql("int4range[]")
  }
  column "_total_vlan_ids" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vlangroup_owner_id_3a50b541_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlangroup_scope_type_id_6606a755_fk_django_content_type_id" {
    columns     = [column.scope_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vlangroup_tenant_id_29197fca_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vlangr_scope_t_9da557_idx" {
    columns = [column.scope_type_id, column.scope_id]
  }
  index "ipam_vlangroup_owner_id_3a50b541" {
    columns = [column.owner_id]
  }
  index "ipam_vlangroup_scope_type_id_6606a755" {
    columns = [column.scope_type_id]
  }
  index "ipam_vlangroup_slug_40abcf6b" {
    columns = [column.slug]
  }
  index "ipam_vlangroup_slug_40abcf6b_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_vlangroup_tenant_id_29197fca" {
    columns = [column.tenant_id]
  }
  check "ipam_vlangroup__total_vlan_ids_check" {
    expr = "(_total_vlan_ids >= 0)"
  }
  check "ipam_vlangroup_scope_id_check" {
    expr = "(scope_id >= 0)"
  }
  unique "ipam_vlangroup_unique_scope_name" {
    columns = [column.scope_type_id, column.scope_id, column.name]
  }
  unique "ipam_vlangroup_unique_scope_slug" {
    columns = [column.scope_type_id, column.scope_id, column.slug]
  }
}
table "ipam_vlantranslationpolicy" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vlantranslationpolicy_owner_id_f4e1cb82_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vlantranslationpolicy_name_17e0a007_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_vlantranslationpolicy_owner_id_f4e1cb82" {
    columns = [column.owner_id]
  }
  unique "ipam_vlantranslationpolicy_name_key" {
    columns = [column.name]
  }
}
table "ipam_vlantranslationrule" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "local_vid" {
    null = false
    type = smallint
  }
  column "remote_vid" {
    null = false
    type = smallint
  }
  column "policy_id" {
    null = false
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vlantranslation_policy_id_09157735_fk_ipam_vlan" {
    columns     = [column.policy_id]
    ref_columns = [table.ipam_vlantranslationpolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vlantranslationrule_policy_id_09157735" {
    columns = [column.policy_id]
  }
  check "ipam_vlantranslationrule_local_vid_check" {
    expr = "(local_vid >= 0)"
  }
  check "ipam_vlantranslationrule_remote_vid_check" {
    expr = "(remote_vid >= 0)"
  }
  unique "ipam_vlantranslationrule_unique_policy_local_vid" {
    columns = [column.policy_id, column.local_vid]
  }
  unique "ipam_vlantranslationrule_unique_policy_remote_vid" {
    columns = [column.policy_id, column.remote_vid]
  }
}
table "ipam_vrf" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "rd" {
    null = true
    type = character_varying(21)
  }
  column "enforce_unique" {
    null = false
    type = boolean
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vrf_owner_id_9b591781_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vrf_tenant_id_498b0051_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vrf_owner_id_9b591781" {
    columns = [column.owner_id]
  }
  index "ipam_vrf_rd_0ac1bde1_like" {
    on {
      column = column.rd
      ops    = varchar_pattern_ops
    }
  }
  index "ipam_vrf_tenant_id_498b0051" {
    columns = [column.tenant_id]
  }
  unique "ipam_vrf_rd_key" {
    columns = [column.rd]
  }
}
table "ipam_vrf_export_targets" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "vrf_id" {
    null = false
    type = bigint
  }
  column "routetarget_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vrf_export_targ_routetarget_id_8d9319f7_fk_ipam_rout" {
    columns     = [column.routetarget_id]
    ref_columns = [table.ipam_routetarget.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vrf_export_targets_vrf_id_6f4875c4_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vrf_export_targets_routetarget_id_8d9319f7" {
    columns = [column.routetarget_id]
  }
  index "ipam_vrf_export_targets_vrf_id_6f4875c4" {
    columns = [column.vrf_id]
  }
  unique "ipam_vrf_export_targets_vrf_id_routetarget_id_63ba8c62_uniq" {
    columns = [column.vrf_id, column.routetarget_id]
  }
}
table "ipam_vrf_import_targets" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "vrf_id" {
    null = false
    type = bigint
  }
  column "routetarget_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_vrf_import_targ_routetarget_id_0e05b144_fk_ipam_rout" {
    columns     = [column.routetarget_id]
    ref_columns = [table.ipam_routetarget.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_vrf_import_targets_vrf_id_ed491b19_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_vrf_import_targets_routetarget_id_0e05b144" {
    columns = [column.routetarget_id]
  }
  index "ipam_vrf_import_targets_vrf_id_ed491b19" {
    columns = [column.vrf_id]
  }
  unique "ipam_vrf_import_targets_vrf_id_routetarget_id_399b155f_uniq" {
    columns = [column.vrf_id, column.routetarget_id]
  }
}
table "social_auth_association" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "server_url" {
    null = false
    type = character_varying(255)
  }
  column "handle" {
    null = false
    type = character_varying(255)
  }
  column "secret" {
    null = false
    type = character_varying(255)
  }
  column "issued" {
    null = false
    type = integer
  }
  column "lifetime" {
    null = false
    type = integer
  }
  column "assoc_type" {
    null = false
    type = character_varying(64)
  }
  primary_key {
    columns = [column.id]
  }
  unique "social_auth_association_server_url_handle_078befa2_uniq" {
    columns = [column.server_url, column.handle]
  }
}
table "social_auth_code" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "code" {
    null = false
    type = character_varying(32)
  }
  column "verified" {
    null = false
    type = boolean
  }
  column "timestamp" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  index "social_auth_code_code_a2393167" {
    columns = [column.code]
  }
  index "social_auth_code_code_a2393167_like" {
    on {
      column = column.code
      ops    = varchar_pattern_ops
    }
  }
  index "social_auth_code_timestamp_176b341f" {
    columns = [column.timestamp]
  }
  unique "social_auth_code_email_code_801b2d02_uniq" {
    columns = [column.email, column.code]
  }
}
table "social_auth_nonce" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "server_url" {
    null = false
    type = character_varying(255)
  }
  column "timestamp" {
    null = false
    type = integer
  }
  column "salt" {
    null = false
    type = character_varying(65)
  }
  primary_key {
    columns = [column.id]
  }
  unique "social_auth_nonce_server_url_timestamp_salt_f6284463_uniq" {
    columns = [column.server_url, column.timestamp, column.salt]
  }
}
table "social_auth_partial" {
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
    type = character_varying(32)
  }
  column "next_step" {
    null = false
    type = smallint
  }
  column "backend" {
    null = false
    type = character_varying(32)
  }
  column "timestamp" {
    null = false
    type = timestamptz
  }
  column "data" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "social_auth_partial_timestamp_50f2119f" {
    columns = [column.timestamp]
  }
  index "social_auth_partial_token_3017fea3" {
    columns = [column.token]
  }
  index "social_auth_partial_token_3017fea3_like" {
    on {
      column = column.token
      ops    = varchar_pattern_ops
    }
  }
  check "social_auth_partial_next_step_check" {
    expr = "(next_step >= 0)"
  }
}
table "social_auth_usersocialauth" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "provider" {
    null = false
    type = character_varying(32)
  }
  column "uid" {
    null = false
    type = character_varying(255)
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "created" {
    null = false
    type = timestamptz
  }
  column "modified" {
    null = false
    type = timestamptz
  }
  column "extra_data" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "social_auth_usersocialauth_user_id_17d28448_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "social_auth_usersocialauth_uid_796e51dc" {
    columns = [column.uid]
  }
  index "social_auth_usersocialauth_uid_796e51dc_like" {
    on {
      column = column.uid
      ops    = varchar_pattern_ops
    }
  }
  index "social_auth_usersocialauth_user_id_17d28448" {
    columns = [column.user_id]
  }
  check "user_social_auth_uid_required" {
    expr = "(NOT ((uid)::text = ''::text))"
  }
  unique "social_auth_usersocialauth_provider_uid_e6b5e668_uniq" {
    columns = [column.provider, column.uid]
  }
}
table "taggit_tag" {
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
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  index "taggit_tag_name_58eb2ed9_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "taggit_tag_slug_6be58b2c_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "taggit_tag_name_key" {
    columns = [column.name]
  }
  unique "taggit_tag_slug_key" {
    columns = [column.slug]
  }
}
table "taggit_taggeditem" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "object_id" {
    null = false
    type = integer
  }
  column "content_type_id" {
    null = false
    type = integer
  }
  column "tag_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "taggit_taggeditem_content_type_id_9957a03c_fk_django_co" {
    columns     = [column.content_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "taggit_taggeditem_tag_id_f4f5b767_fk_taggit_tag_id" {
    columns     = [column.tag_id]
    ref_columns = [table.taggit_tag.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "taggit_tagg_content_8fc721_idx" {
    columns = [column.content_type_id, column.object_id]
  }
  index "taggit_taggeditem_content_type_id_9957a03c" {
    columns = [column.content_type_id]
  }
  index "taggit_taggeditem_object_id_e2d7d1df" {
    columns = [column.object_id]
  }
  index "taggit_taggeditem_tag_id_f4f5b767" {
    columns = [column.tag_id]
  }
  unique "taggit_taggeditem_content_type_id_object_id_tag_id_4bb97a8e_uni" {
    columns = [column.content_type_id, column.object_id, column.tag_id]
  }
}
table "tenancy_contact" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "title" {
    null = false
    type = character_varying(100)
  }
  column "phone" {
    null = false
    type = character_varying(50)
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "address" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "link" {
    null = false
    type = character_varying(200)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_contact_owner_id_9d93abff_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_contact_owner_id_9d93abff" {
    columns = [column.owner_id]
  }
}
table "tenancy_contact_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "contact_id" {
    null = false
    type = bigint
  }
  column "contactgroup_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_contact_grou_contact_id_84c9d84f_fk_tenancy_c" {
    columns     = [column.contact_id]
    ref_columns = [table.tenancy_contact.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_contact_grou_contactgroup_id_5c8d6c5a_fk_tenancy_c" {
    columns     = [column.contactgroup_id]
    ref_columns = [table.tenancy_contactgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_contact_groups_contact_id_84c9d84f" {
    columns = [column.contact_id]
  }
  index "tenancy_contact_groups_contactgroup_id_5c8d6c5a" {
    columns = [column.contactgroup_id]
  }
  unique "tenancy_contact_groups_contact_id_contactgroup_id_f4434f2c_uniq" {
    columns = [column.contactgroup_id, column.contact_id]
  }
}
table "tenancy_contactassignment" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "priority" {
    null = true
    type = character_varying(50)
  }
  column "contact_id" {
    null = false
    type = bigint
  }
  column "object_type_id" {
    null = false
    type = integer
  }
  column "role_id" {
    null = false
    type = bigint
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_contactassig_contact_id_5302baf0_fk_tenancy_c" {
    columns     = [column.contact_id]
    ref_columns = [table.tenancy_contact.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_contactassig_object_type_id_48881567_fk_django_co" {
    columns     = [column.object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_contactassig_role_id_fc08bfb5_fk_tenancy_c" {
    columns     = [column.role_id]
    ref_columns = [table.tenancy_contactrole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_con_object__6f20f7_idx" {
    columns = [column.object_type_id, column.object_id]
  }
  index "tenancy_contactassignment_contact_id_5302baf0" {
    columns = [column.contact_id]
  }
  index "tenancy_contactassignment_content_type_id_0c3f0c67" {
    columns = [column.object_type_id]
  }
  index "tenancy_contactassignment_role_id_fc08bfb5" {
    columns = [column.role_id]
  }
  check "tenancy_contactassignment_object_id_check" {
    expr = "(object_id >= 0)"
  }
  unique "tenancy_contactassignment_unique_object_contact_role" {
    columns = [column.object_type_id, column.object_id, column.contact_id, column.role_id]
  }
}
table "tenancy_contactgroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_contactgroup_owner_id_4bb044c2_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_contactgroup_parent_id_c087d69f_fk_tenancy_c" {
    columns     = [column.parent_id]
    ref_columns = [table.tenancy_contactgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_contactgroup_owner_id_4bb044c2" {
    columns = [column.owner_id]
  }
  index "tenancy_contactgroup_parent_id_c087d69f" {
    columns = [column.parent_id]
  }
  index "tenancy_contactgroup_slug_5b0f3e75" {
    columns = [column.slug]
  }
  index "tenancy_contactgroup_slug_5b0f3e75_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "tenancy_contactgroup_tree_d2ce" {
    columns = [column.tree_id, column.lft]
  }
  index "tenancy_contactgroup_tree_id_57456c98" {
    columns = [column.tree_id]
  }
  check "tenancy_contactgroup_level_check" {
    expr = "(level >= 0)"
  }
  check "tenancy_contactgroup_lft_check" {
    expr = "(lft >= 0)"
  }
  check "tenancy_contactgroup_rght_check" {
    expr = "(rght >= 0)"
  }
  check "tenancy_contactgroup_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "tenancy_contactgroup_unique_parent_name" {
    columns = [column.parent_id, column.name]
  }
}
table "tenancy_contactrole" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_contactrole_owner_id_3677102e_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_contactrole_name_44b01a1f_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "tenancy_contactrole_owner_id_3677102e" {
    columns = [column.owner_id]
  }
  index "tenancy_contactrole_slug_c5837d7d_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "tenancy_contactrole_name_key" {
    columns = [column.name]
  }
  unique "tenancy_contactrole_slug_key" {
    columns = [column.slug]
  }
}
table "tenancy_tenant" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_tenant_group_id_7daef6f4_fk_tenancy_tenantgroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.tenancy_tenantgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_tenant_owner_id_02823f0b_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_tenant_group_id_7daef6f4" {
    columns = [column.group_id]
  }
  index "tenancy_tenant_owner_id_02823f0b" {
    columns = [column.owner_id]
  }
  index "tenancy_tenant_slug_0716575e" {
    columns = [column.slug]
  }
  index "tenancy_tenant_slug_0716575e_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "tenancy_tenant_unique_name" {
    unique  = true
    columns = [column.name]
    where   = "(group_id IS NULL)"
  }
  index "tenancy_tenant_unique_slug" {
    unique  = true
    columns = [column.slug]
    where   = "(group_id IS NULL)"
  }
  unique "tenancy_tenant_unique_group_name" {
    columns = [column.group_id, column.name]
  }
  unique "tenancy_tenant_unique_group_slug" {
    columns = [column.group_id, column.slug]
  }
}
table "tenancy_tenantgroup" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "tenancy_tenantgroup_owner_id_a4f64bbd_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "tenancy_tenantgroup_parent_id_2542fc18_fk_tenancy_t" {
    columns     = [column.parent_id]
    ref_columns = [table.tenancy_tenantgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "tenancy_tenantgroup_name_53363199_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "tenancy_tenantgroup_owner_id_a4f64bbd" {
    columns = [column.owner_id]
  }
  index "tenancy_tenantgroup_parent_id_2542fc18" {
    columns = [column.parent_id]
  }
  index "tenancy_tenantgroup_slug_e2af1cb6_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "tenancy_tenantgroup_tree_id_769a98bf" {
    columns = [column.tree_id]
  }
  index "tenancy_tenantgroup_tree_ifebc" {
    columns = [column.tree_id, column.lft]
  }
  check "tenancy_tenantgroup_level_check" {
    expr = "(level >= 0)"
  }
  check "tenancy_tenantgroup_lft_check" {
    expr = "(lft >= 0)"
  }
  check "tenancy_tenantgroup_rght_check" {
    expr = "(rght >= 0)"
  }
  check "tenancy_tenantgroup_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "tenancy_tenantgroup_name_key" {
    columns = [column.name]
  }
  unique "tenancy_tenantgroup_slug_key" {
    columns = [column.slug]
  }
}
table "thumbnail_kvstore" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(200)
  }
  column "value" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.key]
  }
  index "thumbnail_kvstore_key_3f850178_like" {
    on {
      column = column.key
      ops    = varchar_pattern_ops
    }
  }
}
table "users_group" {
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
    type = character_varying(150)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  index "users_group_name_5f613b12_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  unique "users_group_name_key" {
    columns = [column.name]
  }
}
table "users_group_object_permissions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "objectpermission_id" {
    null = false
    type = bigint
  }
  column "group_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_group_object_p_group_id_90dd183a_fk_users_gro" {
    columns     = [column.group_id]
    ref_columns = [table.users_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_group_object_p_objectpermission_id_dd489dc4_fk_users_obj" {
    columns     = [column.objectpermission_id]
    ref_columns = [table.users_objectpermission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_group_object_permissions_group_id_90dd183a" {
    columns = [column.group_id]
  }
  index "users_group_object_permissions_objectpermission_id_dd489dc4" {
    columns = [column.objectpermission_id]
  }
  unique "users_group_object_permi_group_id_objectpermissio_db1f8cbe_uniq" {
    columns = [column.objectpermission_id, column.group_id]
  }
}
table "users_group_permissions" {
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
    type = bigint
  }
  column "permission_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_group_permissi_permission_id_d8b9c223_fk_auth_perm" {
    columns     = [column.permission_id]
    ref_columns = [table.auth_permission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_group_permissions_group_id_d48652c3_fk_users_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.users_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_group_permissions_group_id_d48652c3" {
    columns = [column.group_id]
  }
  index "users_group_permissions_permission_id_d8b9c223" {
    columns = [column.permission_id]
  }
  unique "users_group_permissions_group_id_permission_id_b740e518_uniq" {
    columns = [column.group_id, column.permission_id]
  }
}
table "users_objectpermission" {
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
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "actions" {
    null = false
    type = sql("character varying(30)[]")
  }
  column "constraints" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
}
table "users_objectpermission_object_types" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "objectpermission_id" {
    null = false
    type = bigint
  }
  column "contenttype_id" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_objectpermissi_contenttype_id_594b1cc7_fk_django_co" {
    columns     = [column.contenttype_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_objectpermissi_objectpermission_id_38c7d8f5_fk_users_obj" {
    columns     = [column.objectpermission_id]
    ref_columns = [table.users_objectpermission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_objectpermission_obj_objectpermission_id_38c7d8f5" {
    columns = [column.objectpermission_id]
  }
  index "users_objectpermission_object_types_contenttype_id_594b1cc7" {
    columns = [column.contenttype_id]
  }
  unique "users_objectpermission_o_objectpermission_id_cont_7c40d31a_uniq" {
    columns = [column.objectpermission_id, column.contenttype_id]
  }
}
table "users_owner" {
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
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "group_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_owner_group_id_197ecf75_fk_users_ownergroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.users_ownergroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_owner_group_id_197ecf75" {
    columns = [column.group_id]
  }
  index "users_owner_name_b9fd4685_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  unique "users_owner_name_key" {
    columns = [column.name]
  }
}
table "users_owner_user_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "owner_id" {
    null = false
    type = bigint
  }
  column "group_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_owner_user_groups_group_id_7f7a78f5_fk_users_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.users_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_owner_user_groups_owner_id_1d847a5b_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_owner_user_groups_group_id_7f7a78f5" {
    columns = [column.group_id]
  }
  index "users_owner_user_groups_owner_id_1d847a5b" {
    columns = [column.owner_id]
  }
  unique "users_owner_user_groups_owner_id_group_id_2def19f4_uniq" {
    columns = [column.owner_id, column.group_id]
  }
}
table "users_owner_users" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "owner_id" {
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
  foreign_key "users_owner_users_owner_id_efc9b423_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_owner_users_user_id_2b2e2446_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_owner_users_owner_id_efc9b423" {
    columns = [column.owner_id]
  }
  index "users_owner_users_user_id_2b2e2446" {
    columns = [column.user_id]
  }
  unique "users_owner_users_owner_id_user_id_07c6d81d_uniq" {
    columns = [column.owner_id, column.user_id]
  }
}
table "users_ownergroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  primary_key {
    columns = [column.id]
  }
  index "users_ownergroup_name_903b8fd1_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  unique "users_ownergroup_name_key" {
    columns = [column.name]
  }
}
table "users_token" {
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
  column "expires" {
    null = true
    type = timestamptz
  }
  column "plaintext" {
    null = true
    type = character_varying(40)
  }
  column "write_enabled" {
    null = false
    type = boolean
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "user_id" {
    null = false
    type = bigint
  }
  column "allowed_ips" {
    null = true
    type = sql("cidr[]")
  }
  column "last_used" {
    null = true
    type = timestamptz
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "version" {
    null = false
    type = smallint
  }
  column "key" {
    null = true
    type = character_varying(12)
  }
  column "pepper_id" {
    null = true
    type = smallint
  }
  column "hmac_digest" {
    null = true
    type = character_varying(64)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_token_user_id_af964690_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_token_key_820deccd_like" {
    on {
      column = column.key
      ops    = varchar_pattern_ops
    }
  }
  index "users_token_plaintext_46c6f315_like" {
    on {
      column = column.plaintext
      ops    = varchar_pattern_ops
    }
  }
  index "users_token_user_id_af964690" {
    columns = [column.user_id]
  }
  check "enforce_version_dependent_fields" {
    expr = "(((hmac_digest IS NULL) AND (key IS NULL) AND (pepper_id IS NULL) AND (plaintext IS NOT NULL) AND (version = 1)) OR ((hmac_digest IS NOT NULL) AND (key IS NOT NULL) AND (pepper_id IS NOT NULL) AND (plaintext IS NULL) AND (version = 2)))"
  }
  check "users_token_pepper_id_check" {
    expr = "(pepper_id >= 0)"
  }
  check "users_token_version_check" {
    expr = "(version >= 0)"
  }
  unique "users_token_key_key" {
    columns = [column.key]
  }
  unique "users_token_plaintext_key" {
    columns = [column.plaintext]
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
  column "username" {
    null = false
    type = character_varying(150)
  }
  column "first_name" {
    null = false
    type = character_varying(150)
  }
  column "last_name" {
    null = false
    type = character_varying(150)
  }
  column "email" {
    null = false
    type = character_varying(254)
  }
  column "is_active" {
    null = false
    type = boolean
  }
  column "date_joined" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  index "users_user_username_06e46fe6_like" {
    on {
      column = column.username
      ops    = varchar_pattern_ops
    }
  }
  unique "users_user_username_key" {
    columns = [column.username]
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
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "auth_user_groups_user_id_6a12ed8b_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_user_groups_group_id_9afc8d0e_fk_users_group_id" {
    columns     = [column.group_id]
    ref_columns = [table.users_group.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "auth_user_groups_group_id_97559544" {
    columns = [column.group_id]
  }
  index "auth_user_groups_user_id_6a12ed8b" {
    columns = [column.user_id]
  }
  unique "auth_user_groups_user_id_group_id_94350c0c_uniq" {
    columns = [column.user_id, column.group_id]
  }
}
table "users_user_object_permissions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "objectpermission_id" {
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
  foreign_key "users_user_object_pe_objectpermission_id_29b431b4_fk_users_obj" {
    columns     = [column.objectpermission_id]
    ref_columns = [table.users_objectpermission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_user_object_permissions_user_id_9d647aac_fk_users_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "users_user_object_permissions_objectpermission_id_29b431b4" {
    columns = [column.objectpermission_id]
  }
  index "users_user_object_permissions_user_id_9d647aac" {
    columns = [column.user_id]
  }
  unique "users_user_object_permis_user_id_objectpermission_0a98550e_uniq" {
    columns = [column.objectpermission_id, column.user_id]
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
  foreign_key "auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm" {
    columns     = [column.permission_id]
    ref_columns = [table.auth_permission.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "auth_user_user_permissions_permission_id_1fbb5f2c" {
    columns = [column.permission_id]
  }
  index "auth_user_user_permissions_user_id_a95ead1b" {
    columns = [column.user_id]
  }
  unique "auth_user_user_permissions_user_id_permission_id_14a6b632_uniq" {
    columns = [column.user_id, column.permission_id]
  }
}
table "users_userconfig" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "data" {
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
  foreign_key "users_userconfig_user_id_afd44184_fk_auth_user_id" {
    columns     = [column.user_id]
    ref_columns = [table.users_user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  unique "users_userconfig_user_id_key" {
    columns = [column.user_id]
  }
}
table "virtualization_cluster" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "comments" {
    null = false
    type = text
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "type_id" {
    null = false
    type = bigint
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "scope_id" {
    null = true
    type = bigint
  }
  column "scope_type_id" {
    null = true
    type = integer
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_region_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "_site_group_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_clust__location_id_f553e386_fk_dcim_loca" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_clust__site_group_id_7d9bff8f_fk_dcim_site" {
    columns     = [column._site_group_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_clust_group_id_de379828_fk_virtualiz" {
    columns     = [column.group_id]
    ref_columns = [table.virtualization_clustergroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_clust_scope_type_id_c49d797a_fk_django_co" {
    columns     = [column.scope_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_clust_type_id_4efafb0a_fk_virtualiz" {
    columns     = [column.type_id]
    ref_columns = [table.virtualization_clustertype.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_cluster__region_id_9244325e_fk_dcim_region_id" {
    columns     = [column._region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_cluster__site_id_883df848_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_cluster_owner_id_2ea44dea_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_cluster_tenant_id_bc2868d0_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualizat_scope_t_fb3b6e_idx" {
    columns = [column.scope_type_id, column.scope_id]
  }
  index "virtualization_cluster__location_id_f553e386" {
    columns = [column._location_id]
  }
  index "virtualization_cluster__region_id_9244325e" {
    columns = [column._region_id]
  }
  index "virtualization_cluster__site_group_id_7d9bff8f" {
    columns = [column._site_group_id]
  }
  index "virtualization_cluster__site_id_883df848" {
    columns = [column._site_id]
  }
  index "virtualization_cluster_group_id_de379828" {
    columns = [column.group_id]
  }
  index "virtualization_cluster_owner_id_2ea44dea" {
    columns = [column.owner_id]
  }
  index "virtualization_cluster_scope_type_id_c49d797a" {
    columns = [column.scope_type_id]
  }
  index "virtualization_cluster_tenant_id_bc2868d0" {
    columns = [column.tenant_id]
  }
  index "virtualization_cluster_type_id_4efafb0a" {
    columns = [column.type_id]
  }
  check "virtualization_cluster_scope_id_check" {
    expr = "(scope_id >= 0)"
  }
  unique "virtualization_cluster_unique__site_name" {
    columns = [column._site_id, column.name]
  }
  unique "virtualization_cluster_unique_group_name" {
    columns = [column.group_id, column.name]
  }
}
table "virtualization_clustergroup" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_clustergroup_owner_id_a865db22_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_clustergroup_name_4fcd26b4_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "virtualization_clustergroup_owner_id_a865db22" {
    columns = [column.owner_id]
  }
  index "virtualization_clustergroup_slug_57ca1d23_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "virtualization_clustergroup_name_key" {
    columns = [column.name]
  }
  unique "virtualization_clustergroup_slug_key" {
    columns = [column.slug]
  }
}
table "virtualization_clustertype" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_clustertype_owner_id_7284f9e4_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_clustertype_name_ea854d3d_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "virtualization_clustertype_owner_id_7284f9e4" {
    columns = [column.owner_id]
  }
  index "virtualization_clustertype_slug_8ee4d0e0_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "virtualization_clustertype_name_key" {
    columns = [column.name]
  }
  unique "virtualization_clustertype_slug_key" {
    columns = [column.slug]
  }
}
table "virtualization_virtualdisk" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "size" {
    null = false
    type = integer
  }
  column "virtual_machine_id" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_virtu_virtual_machine_id_7bc8b6c2_fk_virtualiz" {
    columns     = [column.virtual_machine_id]
    ref_columns = [table.virtualization_virtualmachine.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtualdisk_owner_id_2e14487d_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_virtualdisk_owner_id_2e14487d" {
    columns = [column.owner_id]
  }
  index "virtualization_virtualdisk_virtual_machine_id_7bc8b6c2" {
    columns = [column.virtual_machine_id]
  }
  check "virtualization_virtualdisk_size_check" {
    expr = "(size >= 0)"
  }
  unique "virtualization_virtualdisk_unique_virtual_machine_name" {
    columns = [column.virtual_machine_id, column.name]
  }
}
table "virtualization_virtualmachine" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "local_context_data" {
    null = true
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "vcpus" {
    null = true
    type = numeric(6,2)
  }
  column "memory" {
    null = true
    type = integer
  }
  column "disk" {
    null = true
    type = integer
  }
  column "comments" {
    null = false
    type = text
  }
  column "cluster_id" {
    null = true
    type = bigint
  }
  column "platform_id" {
    null = true
    type = bigint
  }
  column "primary_ip4_id" {
    null = true
    type = bigint
  }
  column "primary_ip6_id" {
    null = true
    type = bigint
  }
  column "role_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "site_id" {
    null = true
    type = bigint
  }
  column "device_id" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "interface_count" {
    null = false
    type = bigint
  }
  column "config_template_id" {
    null = true
    type = bigint
  }
  column "virtual_disk_count" {
    null = false
    type = bigint
  }
  column "serial" {
    null = false
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "start_on_boot" {
    null = false
    type = character_varying(32)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_virtu_cluster_id_6c9f9047_fk_virtualiz" {
    columns     = [column.cluster_id]
    ref_columns = [table.virtualization_cluster.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_config_template_id_d7fc7874_fk_extras_co" {
    columns     = [column.config_template_id]
    ref_columns = [table.extras_configtemplate.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_device_id_5a49ed18_fk_dcim_devi" {
    columns     = [column.device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_owner_id_f6593561_fk_users_own" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_platform_id_a6c5ccb2_fk_dcim_plat" {
    columns     = [column.platform_id]
    ref_columns = [table.dcim_platform.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_primary_ip4_id_942e42ae_fk_ipam_ipad" {
    columns     = [column.primary_ip4_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_primary_ip6_id_b7904e73_fk_ipam_ipad" {
    columns     = [column.primary_ip6_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_role_id_0cc898f9_fk_dcim_devi" {
    columns     = [column.role_id]
    ref_columns = [table.dcim_devicerole.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtu_tenant_id_d00d1d77_fk_tenancy_t" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_virtualmachine_site_id_54475a27_fk_dcim_site_id" {
    columns     = [column.site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_virtualmachine_cluster_id_6c9f9047" {
    columns = [column.cluster_id]
  }
  index "virtualization_virtualmachine_config_template_id_d7fc7874" {
    columns = [column.config_template_id]
  }
  index "virtualization_virtualmachine_device_id_5a49ed18" {
    columns = [column.device_id]
  }
  index "virtualization_virtualmachine_owner_id_f6593561" {
    columns = [column.owner_id]
  }
  index "virtualization_virtualmachine_platform_id_a6c5ccb2" {
    columns = [column.platform_id]
  }
  index "virtualization_virtualmachine_role_id_0cc898f9" {
    columns = [column.role_id]
  }
  index "virtualization_virtualmachine_site_id_54475a27" {
    columns = [column.site_id]
  }
  index "virtualization_virtualmachine_tenant_id_d00d1d77" {
    columns = [column.tenant_id]
  }
  index "virtualization_virtualmachine_unique_name_cluster" {
    unique = true
    where  = "(tenant_id IS NULL)"
    on {
      expr = "lower((name)::text)"
    }
    on {
      column = column.cluster_id
    }
  }
  index "virtualization_virtualmachine_unique_name_cluster_tenant" {
    unique = true
    on {
      expr = "lower((name)::text)"
    }
    on {
      column = column.cluster_id
    }
    on {
      column = column.tenant_id
    }
  }
  check "virtualization_virtualmachine_disk_check" {
    expr = "(disk >= 0)"
  }
  check "virtualization_virtualmachine_memory_check" {
    expr = "(memory >= 0)"
  }
  unique "virtualization_virtualmachine_primary_ip4_id_key" {
    columns = [column.primary_ip4_id]
  }
  unique "virtualization_virtualmachine_primary_ip6_id_key" {
    columns = [column.primary_ip6_id]
  }
}
table "virtualization_vminterface" {
  schema = schema.public
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "mtu" {
    null = true
    type = integer
  }
  column "mode" {
    null = true
    type = character_varying(50)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "_name" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "untagged_vlan_id" {
    null = true
    type = bigint
  }
  column "virtual_machine_id" {
    null = false
    type = bigint
  }
  column "bridge_id" {
    null = true
    type = bigint
  }
  column "vrf_id" {
    null = true
    type = bigint
  }
  column "vlan_translation_policy_id" {
    null = true
    type = bigint
  }
  column "qinq_svlan_id" {
    null = true
    type = bigint
  }
  column "primary_mac_address_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_vmint_bridge_id_7462b91e_fk_virtualiz" {
    columns     = [column.bridge_id]
    ref_columns = [table.virtualization_vminterface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_parent_id_f86958e1_fk_virtualiz" {
    columns     = [column.parent_id]
    ref_columns = [table.virtualization_vminterface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_primary_mac_address__7a6c9b66_fk_dcim_maca" {
    columns     = [column.primary_mac_address_id]
    ref_columns = [table.dcim_macaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_qinq_svlan_id_afacb024_fk_ipam_vlan" {
    columns     = [column.qinq_svlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_untagged_vlan_id_aea4fc69_fk_ipam_vlan" {
    columns     = [column.untagged_vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_virtual_machine_id_e9f89829_fk_virtualiz" {
    columns     = [column.virtual_machine_id]
    ref_columns = [table.virtualization_virtualmachine.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_vlan_translation_pol_938e6637_fk_ipam_vlan" {
    columns     = [column.vlan_translation_policy_id]
    ref_columns = [table.ipam_vlantranslationpolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vminterface_owner_id_486754ee_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vminterface_vrf_id_4b570a8c_fk_ipam_vrf_id" {
    columns     = [column.vrf_id]
    ref_columns = [table.ipam_vrf.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_vminterface_bridge_id_7462b91e" {
    columns = [column.bridge_id]
  }
  index "virtualization_vminterface_owner_id_486754ee" {
    columns = [column.owner_id]
  }
  index "virtualization_vminterface_parent_id_f86958e1" {
    columns = [column.parent_id]
  }
  index "virtualization_vminterface_qinq_svlan_id_afacb024" {
    columns = [column.qinq_svlan_id]
  }
  index "virtualization_vminterface_untagged_vlan_id_aea4fc69" {
    columns = [column.untagged_vlan_id]
  }
  index "virtualization_vminterface_virtual_machine_id_e9f89829" {
    columns = [column.virtual_machine_id]
  }
  index "virtualization_vminterface_vlan_translation_policy_id_938e6637" {
    columns = [column.vlan_translation_policy_id]
  }
  index "virtualization_vminterface_vrf_id_4b570a8c" {
    columns = [column.vrf_id]
  }
  check "virtualization_vminterface_mtu_check" {
    expr = "(mtu >= 0)"
  }
  unique "virtualization_vminterface_primary_mac_address_id_key" {
    columns = [column.primary_mac_address_id]
  }
  unique "virtualization_vminterface_unique_virtual_machine_name" {
    columns = [column.virtual_machine_id, column.name]
  }
}
table "virtualization_vminterface_tagged_vlans" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "vminterface_id" {
    null = false
    type = bigint
  }
  column "vlan_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "virtualization_vmint_vlan_id_4e77411e_fk_ipam_vlan" {
    columns     = [column.vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "virtualization_vmint_vminterface_id_904b12de_fk_virtualiz" {
    columns     = [column.vminterface_id]
    ref_columns = [table.virtualization_vminterface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "virtualization_vminterface_tagged_vlans_vlan_id_4e77411e" {
    columns = [column.vlan_id]
  }
  index "virtualization_vminterface_tagged_vlans_vminterface_id_904b12de" {
    columns = [column.vminterface_id]
  }
  unique "virtualization_vminterfa_vminterface_id_vlan_id_27e907db_uniq" {
    columns = [column.vminterface_id, column.vlan_id]
  }
}
table "vpn_ikepolicy" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "version" {
    null = false
    type = smallint
  }
  column "mode" {
    null = true
    type = character_varying
  }
  column "preshared_key" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ikepolicy_owner_id_dbcaf1bd_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ikepolicy_name_5124aa3b_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_ikepolicy_owner_id_dbcaf1bd" {
    columns = [column.owner_id]
  }
  check "vpn_ikepolicy_version_check" {
    expr = "(version >= 0)"
  }
  unique "vpn_ikepolicy_name_key" {
    columns = [column.name]
  }
}
table "vpn_ikepolicy_proposals" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "ikepolicy_id" {
    null = false
    type = bigint
  }
  column "ikeproposal_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ikepolicy_propos_ikepolicy_id_1e1deaab_fk_vpn_ikepo" {
    columns     = [column.ikepolicy_id]
    ref_columns = [table.vpn_ikepolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_ikepolicy_propos_ikeproposal_id_a9ead252_fk_vpn_ikepr" {
    columns     = [column.ikeproposal_id]
    ref_columns = [table.vpn_ikeproposal.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ikepolicy_proposals_ikepolicy_id_1e1deaab" {
    columns = [column.ikepolicy_id]
  }
  index "vpn_ikepolicy_proposals_ikeproposal_id_a9ead252" {
    columns = [column.ikeproposal_id]
  }
  unique "vpn_ikepolicy_proposals_ikepolicy_id_ikeproposal_0c3baa9c_uniq" {
    columns = [column.ikepolicy_id, column.ikeproposal_id]
  }
}
table "vpn_ikeproposal" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "authentication_method" {
    null = false
    type = character_varying
  }
  column "encryption_algorithm" {
    null = false
    type = character_varying
  }
  column "authentication_algorithm" {
    null = true
    type = character_varying
  }
  column "group" {
    null = false
    type = smallint
  }
  column "sa_lifetime" {
    null = true
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ikeproposal_owner_id_018a3e69_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ikeproposal_name_254623b7_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_ikeproposal_owner_id_018a3e69" {
    columns = [column.owner_id]
  }
  check "vpn_ikeproposal_group_check" {
    expr = "(\"group\" >= 0)"
  }
  check "vpn_ikeproposal_sa_lifetime_check" {
    expr = "(sa_lifetime >= 0)"
  }
  unique "vpn_ikeproposal_name_key" {
    columns = [column.name]
  }
}
table "vpn_ipsecpolicy" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "pfs_group" {
    null = true
    type = smallint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ipsecpolicy_owner_id_e976d198_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ipsecpolicy_name_cf28a1aa_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_ipsecpolicy_owner_id_e976d198" {
    columns = [column.owner_id]
  }
  check "vpn_ipsecpolicy_pfs_group_check" {
    expr = "(pfs_group >= 0)"
  }
  unique "vpn_ipsecpolicy_name_key" {
    columns = [column.name]
  }
}
table "vpn_ipsecpolicy_proposals" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "ipsecpolicy_id" {
    null = false
    type = bigint
  }
  column "ipsecproposal_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ipsecpolicy_prop_ipsecpolicy_id_0e7771a1_fk_vpn_ipsec" {
    columns     = [column.ipsecpolicy_id]
    ref_columns = [table.vpn_ipsecpolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_ipsecpolicy_prop_ipsecproposal_id_685fe509_fk_vpn_ipsec" {
    columns     = [column.ipsecproposal_id]
    ref_columns = [table.vpn_ipsecproposal.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ipsecpolicy_proposals_ipsecpolicy_id_0e7771a1" {
    columns = [column.ipsecpolicy_id]
  }
  index "vpn_ipsecpolicy_proposals_ipsecproposal_id_685fe509" {
    columns = [column.ipsecproposal_id]
  }
  unique "vpn_ipsecpolicy_proposal_ipsecpolicy_id_ipsecprop_72096768_uniq" {
    columns = [column.ipsecpolicy_id, column.ipsecproposal_id]
  }
}
table "vpn_ipsecprofile" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "mode" {
    null = false
    type = character_varying
  }
  column "ike_policy_id" {
    null = false
    type = bigint
  }
  column "ipsec_policy_id" {
    null = false
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ipsecprofile_ike_policy_id_4eff5fb9_fk_vpn_ikepolicy_id" {
    columns     = [column.ike_policy_id]
    ref_columns = [table.vpn_ikepolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_ipsecprofile_ipsec_policy_id_e06f2323_fk_vpn_ipsecpolicy_id" {
    columns     = [column.ipsec_policy_id]
    ref_columns = [table.vpn_ipsecpolicy.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_ipsecprofile_owner_id_d7ebc4a0_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ipsecprofile_ike_policy_id_4eff5fb9" {
    columns = [column.ike_policy_id]
  }
  index "vpn_ipsecprofile_ipsec_policy_id_e06f2323" {
    columns = [column.ipsec_policy_id]
  }
  index "vpn_ipsecprofile_name_3ac63c72_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_ipsecprofile_owner_id_d7ebc4a0" {
    columns = [column.owner_id]
  }
  unique "vpn_ipsecprofile_name_key" {
    columns = [column.name]
  }
}
table "vpn_ipsecproposal" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "encryption_algorithm" {
    null = true
    type = character_varying
  }
  column "authentication_algorithm" {
    null = true
    type = character_varying
  }
  column "sa_lifetime_seconds" {
    null = true
    type = integer
  }
  column "sa_lifetime_data" {
    null = true
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_ipsecproposal_owner_id_fdb3b755_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_ipsecproposal_name_2fb98e2b_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_ipsecproposal_owner_id_fdb3b755" {
    columns = [column.owner_id]
  }
  check "vpn_ipsecproposal_sa_lifetime_data_check" {
    expr = "(sa_lifetime_data >= 0)"
  }
  check "vpn_ipsecproposal_sa_lifetime_seconds_check" {
    expr = "(sa_lifetime_seconds >= 0)"
  }
  unique "vpn_ipsecproposal_name_key" {
    columns = [column.name]
  }
}
table "vpn_l2vpn" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "type" {
    null = false
    type = character_varying(50)
  }
  column "identifier" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_l2vpn_owner_id_894bd11d_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_l2vpn_tenant_id_57ec8f92_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_l2vpn_name_8824eda5_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_l2vpn_owner_id_894bd11d" {
    columns = [column.owner_id]
  }
  index "vpn_l2vpn_slug_76b5a174_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_l2vpn_tenant_id_57ec8f92" {
    columns = [column.tenant_id]
  }
  unique "vpn_l2vpn_name_key" {
    columns = [column.name]
  }
  unique "vpn_l2vpn_slug_key" {
    columns = [column.slug]
  }
}
table "vpn_l2vpn_export_targets" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "l2vpn_id" {
    null = false
    type = bigint
  }
  column "routetarget_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_l2vpn_export_ta_routetarget_id_5ccb758b_fk_ipam_rout" {
    columns     = [column.routetarget_id]
    ref_columns = [table.ipam_routetarget.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_l2vpn_export_targets_l2vpn_id_8749bbe8_fk_ipam_l2vpn_id" {
    columns     = [column.l2vpn_id]
    ref_columns = [table.vpn_l2vpn.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_l2vpn_export_targets_l2vpn_id_8749bbe8" {
    columns = [column.l2vpn_id]
  }
  index "ipam_l2vpn_export_targets_routetarget_id_5ccb758b" {
    columns = [column.routetarget_id]
  }
  unique "ipam_l2vpn_export_targets_l2vpn_id_routetarget_id_eea90661_uniq" {
    columns = [column.l2vpn_id, column.routetarget_id]
  }
}
table "vpn_l2vpn_import_targets" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "l2vpn_id" {
    null = false
    type = bigint
  }
  column "routetarget_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ipam_l2vpn_import_ta_routetarget_id_58a188b2_fk_ipam_rout" {
    columns     = [column.routetarget_id]
    ref_columns = [table.ipam_routetarget.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ipam_l2vpn_import_targets_l2vpn_id_731f5bb4_fk_ipam_l2vpn_id" {
    columns     = [column.l2vpn_id]
    ref_columns = [table.vpn_l2vpn.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ipam_l2vpn_import_targets_l2vpn_id_731f5bb4" {
    columns = [column.l2vpn_id]
  }
  index "ipam_l2vpn_import_targets_routetarget_id_58a188b2" {
    columns = [column.routetarget_id]
  }
  unique "ipam_l2vpn_import_targets_l2vpn_id_routetarget_id_96af344c_uniq" {
    columns = [column.l2vpn_id, column.routetarget_id]
  }
}
table "vpn_l2vpntermination" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "assigned_object_id" {
    null = false
    type = bigint
  }
  column "assigned_object_type_id" {
    null = false
    type = integer
  }
  column "l2vpn_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_l2vpntermination_assigned_object_type_id_f063b865_fk_django" {
    columns     = [column.assigned_object_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_l2vpntermination_l2vpn_id_f5367bbe_fk_vpn_l2vpn_id" {
    columns     = [column.l2vpn_id]
    ref_columns = [table.vpn_l2vpn.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_l2vpntermination_assigned_object_type_id_f063b865" {
    columns = [column.assigned_object_type_id]
  }
  index "vpn_l2vpntermination_l2vpn_id_f5367bbe" {
    columns = [column.l2vpn_id]
  }
  check "vpn_l2vpntermination_assigned_object_id_check" {
    expr = "(assigned_object_id >= 0)"
  }
  unique "vpn_l2vpntermination_assigned_object" {
    columns = [column.assigned_object_type_id, column.assigned_object_id]
  }
}
table "vpn_tunnel" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "comments" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "encapsulation" {
    null = false
    type = character_varying(50)
  }
  column "tunnel_id" {
    null = true
    type = bigint
  }
  column "ipsec_profile_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_tunnel_group_id_56b1e7f7_fk_vpn_tunnelgroup_id" {
    columns     = [column.group_id]
    ref_columns = [table.vpn_tunnelgroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_tunnel_ipsec_profile_id_fd0361c5_fk_vpn_ipsecprofile_id" {
    columns     = [column.ipsec_profile_id]
    ref_columns = [table.vpn_ipsecprofile.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_tunnel_owner_id_d04ee1fb_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_tunnel_tenant_id_f3df2ab3_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_tunnel_group_id_56b1e7f7" {
    columns = [column.group_id]
  }
  index "vpn_tunnel_ipsec_profile_id_fd0361c5" {
    columns = [column.ipsec_profile_id]
  }
  index "vpn_tunnel_name" {
    unique  = true
    columns = [column.name]
    where   = "(group_id IS NULL)"
  }
  index "vpn_tunnel_name_f060beab_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_tunnel_owner_id_d04ee1fb" {
    columns = [column.owner_id]
  }
  index "vpn_tunnel_tenant_id_f3df2ab3" {
    columns = [column.tenant_id]
  }
  check "vpn_tunnel_tunnel_id_check" {
    expr = "(tunnel_id >= 0)"
  }
  unique "vpn_tunnel_group_name" {
    columns = [column.group_id, column.name]
  }
  unique "vpn_tunnel_name_key" {
    columns = [column.name]
  }
}
table "vpn_tunnelgroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_tunnelgroup_owner_id_64609bfe_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_tunnelgroup_name_9f6ebf92_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "vpn_tunnelgroup_owner_id_64609bfe" {
    columns = [column.owner_id]
  }
  index "vpn_tunnelgroup_slug_9e614d62_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  unique "vpn_tunnelgroup_name_key" {
    columns = [column.name]
  }
  unique "vpn_tunnelgroup_slug_key" {
    columns = [column.slug]
  }
}
table "vpn_tunneltermination" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "role" {
    null = false
    type = character_varying(50)
  }
  column "termination_id" {
    null = true
    type = bigint
  }
  column "termination_type_id" {
    null = false
    type = integer
  }
  column "outside_ip_id" {
    null = true
    type = bigint
  }
  column "tunnel_id" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "vpn_tunnelterminatio_outside_ip_id_2c6f3a7c_fk_ipam_ipad" {
    columns     = [column.outside_ip_id]
    ref_columns = [table.ipam_ipaddress.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_tunnelterminatio_termination_type_id_e546f7a1_fk_django_co" {
    columns     = [column.termination_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "vpn_tunneltermination_tunnel_id_962efa25_fk_vpn_tunnel_id" {
    columns     = [column.tunnel_id]
    ref_columns = [table.vpn_tunnel.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "vpn_tunneltermination_outside_ip_id_2c6f3a7c" {
    columns = [column.outside_ip_id]
  }
  index "vpn_tunneltermination_termination_type_id_e546f7a1" {
    columns = [column.termination_type_id]
  }
  index "vpn_tunneltermination_tunnel_id_962efa25" {
    columns = [column.tunnel_id]
  }
  check "vpn_tunneltermination_termination_id_check" {
    expr = "(termination_id >= 0)"
  }
  unique "vpn_tunneltermination_termination" {
    columns = [column.termination_type_id, column.termination_id]
  }
}
table "wireless_wirelesslan" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "ssid" {
    null = false
    type = character_varying(32)
  }
  column "group_id" {
    null = true
    type = bigint
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "auth_cipher" {
    null = true
    type = character_varying(50)
  }
  column "auth_psk" {
    null = false
    type = character_varying(64)
  }
  column "auth_type" {
    null = true
    type = character_varying(50)
  }
  column "vlan_id" {
    null = true
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "_location_id" {
    null = true
    type = bigint
  }
  column "_region_id" {
    null = true
    type = bigint
  }
  column "_site_id" {
    null = true
    type = bigint
  }
  column "_site_group_id" {
    null = true
    type = bigint
  }
  column "scope_id" {
    null = true
    type = bigint
  }
  column "scope_type_id" {
    null = true
    type = integer
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "wireless_wirelesslan__location_id_c742912f_fk_dcim_location_id" {
    columns     = [column._location_id]
    ref_columns = [table.dcim_location.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan__region_id_fd2a93ee_fk_dcim_region_id" {
    columns     = [column._region_id]
    ref_columns = [table.dcim_region.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan__site_group_id_d61285cc_fk_dcim_site" {
    columns     = [column._site_group_id]
    ref_columns = [table.dcim_sitegroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan__site_id_5dce5f6f_fk_dcim_site_id" {
    columns     = [column._site_id]
    ref_columns = [table.dcim_site.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan_group_id_d9e3d67f_fk_wireless_" {
    columns     = [column.group_id]
    ref_columns = [table.wireless_wirelesslangroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan_owner_id_9ea24eeb_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan_scope_type_id_c3e37d35_fk_django_co" {
    columns     = [column.scope_type_id]
    ref_columns = [table.django_content_type.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan_tenant_id_5dfee941_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslan_vlan_id_d7fa6ccc_fk_ipam_vlan_id" {
    columns     = [column.vlan_id]
    ref_columns = [table.ipam_vlan.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "wireless_wi_scope_t_6740a3_idx" {
    columns = [column.scope_type_id, column.scope_id]
  }
  index "wireless_wirelesslan__location_id_c742912f" {
    columns = [column._location_id]
  }
  index "wireless_wirelesslan__region_id_fd2a93ee" {
    columns = [column._region_id]
  }
  index "wireless_wirelesslan__site_group_id_d61285cc" {
    columns = [column._site_group_id]
  }
  index "wireless_wirelesslan__site_id_5dce5f6f" {
    columns = [column._site_id]
  }
  index "wireless_wirelesslan_group_id_d9e3d67f" {
    columns = [column.group_id]
  }
  index "wireless_wirelesslan_owner_id_9ea24eeb" {
    columns = [column.owner_id]
  }
  index "wireless_wirelesslan_scope_type_id_c3e37d35" {
    columns = [column.scope_type_id]
  }
  index "wireless_wirelesslan_tenant_id_5dfee941" {
    columns = [column.tenant_id]
  }
  index "wireless_wirelesslan_vlan_id_d7fa6ccc" {
    columns = [column.vlan_id]
  }
  check "wireless_wirelesslan_scope_id_check" {
    expr = "(scope_id >= 0)"
  }
}
table "wireless_wirelesslangroup" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "name" {
    null = false
    type = character_varying(100)
  }
  column "slug" {
    null = false
    type = character_varying(100)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "lft" {
    null = false
    type = integer
  }
  column "rght" {
    null = false
    type = integer
  }
  column "tree_id" {
    null = false
    type = integer
  }
  column "level" {
    null = false
    type = integer
  }
  column "parent_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "wireless_wirelesslan_parent_id_37ca8b87_fk_wireless_" {
    columns     = [column.parent_id]
    ref_columns = [table.wireless_wirelesslangroup.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslangroup_owner_id_0ba5f844_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "wireless_wirelesslangroup_fbcd" {
    columns = [column.tree_id, column.lft]
  }
  index "wireless_wirelesslangroup_name_2ffd60c8_like" {
    on {
      column = column.name
      ops    = varchar_pattern_ops
    }
  }
  index "wireless_wirelesslangroup_owner_id_0ba5f844" {
    columns = [column.owner_id]
  }
  index "wireless_wirelesslangroup_parent_id_37ca8b87" {
    columns = [column.parent_id]
  }
  index "wireless_wirelesslangroup_slug_f5d59831_like" {
    on {
      column = column.slug
      ops    = varchar_pattern_ops
    }
  }
  index "wireless_wirelesslangroup_tree_id_eb99115d" {
    columns = [column.tree_id]
  }
  check "wireless_wirelesslangroup_level_check" {
    expr = "(level >= 0)"
  }
  check "wireless_wirelesslangroup_lft_check" {
    expr = "(lft >= 0)"
  }
  check "wireless_wirelesslangroup_rght_check" {
    expr = "(rght >= 0)"
  }
  check "wireless_wirelesslangroup_tree_id_check" {
    expr = "(tree_id >= 0)"
  }
  unique "wireless_wirelesslangroup_name_key" {
    columns = [column.name]
  }
  unique "wireless_wirelesslangroup_slug_key" {
    columns = [column.slug]
  }
  unique "wireless_wirelesslangroup_unique_parent_name" {
    columns = [column.parent_id, column.name]
  }
}
table "wireless_wirelesslink" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
    identity {
      generated = BY_DEFAULT
    }
  }
  column "created" {
    null = true
    type = timestamptz
  }
  column "last_updated" {
    null = true
    type = timestamptz
  }
  column "custom_field_data" {
    null = false
    type = jsonb
  }
  column "ssid" {
    null = false
    type = character_varying(32)
  }
  column "status" {
    null = false
    type = character_varying(50)
  }
  column "description" {
    null = false
    type = character_varying(200)
  }
  column "auth_cipher" {
    null = true
    type = character_varying(50)
  }
  column "auth_psk" {
    null = false
    type = character_varying(64)
  }
  column "auth_type" {
    null = true
    type = character_varying(50)
  }
  column "_interface_a_device_id" {
    null = true
    type = bigint
  }
  column "_interface_b_device_id" {
    null = true
    type = bigint
  }
  column "interface_a_id" {
    null = false
    type = bigint
  }
  column "interface_b_id" {
    null = false
    type = bigint
  }
  column "tenant_id" {
    null = true
    type = bigint
  }
  column "comments" {
    null = false
    type = text
  }
  column "_abs_distance" {
    null = true
    type = numeric(13,4)
  }
  column "distance" {
    null = true
    type = numeric(8,2)
  }
  column "distance_unit" {
    null = true
    type = character_varying(50)
  }
  column "owner_id" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "wireless_wirelesslin__interface_a_device__6c8e042e_fk_dcim_devi" {
    columns     = [column._interface_a_device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslin__interface_b_device__43d5101a_fk_dcim_devi" {
    columns     = [column._interface_b_device_id]
    ref_columns = [table.dcim_device.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslin_interface_a_id_bc9e37fd_fk_dcim_inte" {
    columns     = [column.interface_a_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslin_interface_b_id_a82fb2ee_fk_dcim_inte" {
    columns     = [column.interface_b_id]
    ref_columns = [table.dcim_interface.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslink_owner_id_103f9be1_fk_users_owner_id" {
    columns     = [column.owner_id]
    ref_columns = [table.users_owner.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "wireless_wirelesslink_tenant_id_4c0638ee_fk_tenancy_tenant_id" {
    columns     = [column.tenant_id]
    ref_columns = [table.tenancy_tenant.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "wireless_wirelesslink__interface_a_device_id_6c8e042e" {
    columns = [column._interface_a_device_id]
  }
  index "wireless_wirelesslink__interface_b_device_id_43d5101a" {
    columns = [column._interface_b_device_id]
  }
  index "wireless_wirelesslink_interface_a_id_bc9e37fd" {
    columns = [column.interface_a_id]
  }
  index "wireless_wirelesslink_interface_b_id_a82fb2ee" {
    columns = [column.interface_b_id]
  }
  index "wireless_wirelesslink_owner_id_103f9be1" {
    columns = [column.owner_id]
  }
  index "wireless_wirelesslink_tenant_id_4c0638ee" {
    columns = [column.tenant_id]
  }
  unique "wireless_wirelesslink_unique_interfaces" {
    columns = [column.interface_a_id, column.interface_b_id]
  }
}
schema "public" {
  comment = "standard public schema"
}
