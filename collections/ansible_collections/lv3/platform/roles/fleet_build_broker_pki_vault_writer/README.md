# fleet_build_broker_pki_vault_writer

Installs the sole Dockerhost-side path that can publish the private
`fleet-build-broker` PKI batch. It is not a general secret writer, an API-key
operator tool, or a workload credential path.

The role creates one locked service account whose only permitted SSH public key
is supplied from the Step-CA control host. That key is bound to the control
host source address and an OpenSSH forced command. It cannot obtain a shell,
port forward, agent forward, X11 session, terminal, or arbitrary sudo command.
The forced command invokes a root-only executable with the one fixed principal,
scope, tier, TTL, and use limit.

The executable reads the complete certificate payload once from standard input,
validates the exact ten-record broker batch, reads the existing root-only local
API-key administration file, issues exactly one five-minute single-use writer,
posts the fixed `/broker-pki-batch` endpoint over HTTPS, and revokes that writer
in a `finally` path. Certificate material and either API credential exist only
in process memory; neither is logged, printed, written to a file, returned, or
placed in an Ansible result.

The paired private SSH key is control-plane state and must be provisioned by the
separate root-only PKI handoff rollout. This role fails before changing sshd if
the exact public key is absent. It also refuses a configuration that changes
the Dockerhost loopback API-key endpoint, the HTTPS vault endpoint, token file,
identity, scope, five-minute TTL, or one-use limit.

Do not invoke the transaction manually. A transport timeout after the vault
request is ambiguous: the bridge revokes the writer, returns failure, and does
not retry. Operators must inspect the fixed batch's audit receipt before making
a new issuance attempt; retrying could replace a valid certificate batch.
