# WS-0494: Woodpecker CI network recovery

## Outcome

The managed CI server was restored after its container started without an
attachment to the declared Compose bridge. The host and the bridge could reach
the CI database, so the server was reattached only to its existing named
network. The runtime became healthy, the public endpoint returned successfully,
and a newly delivered pull-request event completed its Woodpecker pipeline.

## Safeguards

- No CI database, repository configuration, workflow, or secret was changed.
- The repair used the existing Compose bridge and did not create a new network.
- The recovery evidence omits private endpoints, webhook data, and credentials.
