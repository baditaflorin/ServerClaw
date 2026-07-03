// One-time interactive OAuth authorization for the Gmail task watcher.
//
// Run this LOCALLY (on your own machine, with a browser), not inside the
// docker container on the guest — it needs to open a real browser and
// receive the redirect on localhost.
//
//   node authorize.js /path/to/client_secret_....json
//
// Prints a refresh token at the end. Save it to
// .local/huly/gmail-watcher-refresh-token (gitignored) — the watcher
// container reads it from there.
'use strict'

const http = require('http')
const { URL } = require('url')
const fs = require('fs')
const { google } = require('googleapis')

const REDIRECT_PORT = 8945
const REDIRECT_URI = `http://localhost:${REDIRECT_PORT}/oauth2callback`
const SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

async function main () {
  const clientSecretPath = process.argv[2]
  if (!clientSecretPath) {
    console.error('usage: node authorize.js /path/to/client_secret_....json')
    process.exit(1)
  }

  const raw = JSON.parse(fs.readFileSync(clientSecretPath, 'utf8'))
  const creds = raw.installed ?? raw.web
  if (creds === undefined) {
    console.error('client secret JSON has neither "installed" nor "web" key')
    process.exit(1)
  }

  const oAuth2Client = new google.auth.OAuth2(creds.client_id, creds.client_secret, REDIRECT_URI)

  const authUrl = oAuth2Client.generateAuthUrl({
    access_type: 'offline',
    prompt: 'consent',
    scope: SCOPES
  })

  console.log('\nOpen this URL in a browser and approve access:\n')
  console.log(authUrl)
  console.log(`\nWaiting for the redirect on ${REDIRECT_URI} ...\n`)

  const code = await new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, REDIRECT_URI)
      if (url.pathname !== '/oauth2callback') {
        res.writeHead(404).end()
        return
      }
      const err = url.searchParams.get('error')
      const authCode = url.searchParams.get('code')
      res.writeHead(200, { 'content-type': 'text/plain' })
      res.end(err ? `Authorization failed: ${err}. You can close this tab.` : 'Authorization complete. You can close this tab.')
      server.close()
      if (err) reject(new Error(err))
      else resolve(authCode)
    })
    server.listen(REDIRECT_PORT)
  })

  const { tokens } = await oAuth2Client.getToken(code)
  if (!tokens.refresh_token) {
    console.error('\nNo refresh_token returned. This usually means you already authorized this client before.')
    console.error('Revoke prior access at https://myaccount.google.com/permissions and re-run this script.')
    process.exit(1)
  }

  console.log('\nRefresh token (save this to .local/huly/gmail-watcher-refresh-token):\n')
  console.log(tokens.refresh_token)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
