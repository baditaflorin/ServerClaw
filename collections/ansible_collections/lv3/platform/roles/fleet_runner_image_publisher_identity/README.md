# fleet_runner_image_publisher_identity

Installs the fixed, non-secret fleet-runner image-publisher identity contract
on the dedicated Builder LXC108 only.

The role is intentionally closed:

- it rejects every inventory host except `0docker_builder` (the Builder
  LXC108 inventory hostname);
- it creates `/etc/fleet-runner` as `root:root` mode `0700`;
- it writes `/etc/fleet-runner/image-publisher.json` as `root:root` mode
  `0600` with the exact payload `{"version":1,"identity":"builder-lxc-108"}`;
- it accepts no credential, registry URL, image name, or user-shell input.

Run it only through the `fleet-runner-image-publisher.yml` playbook with the
dedicated `0docker_builder` inventory hostname. This role does not publish an image,
read a secret, configure registry authentication, or create a network route.
