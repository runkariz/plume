# Authenticate a standalone or API-only app

Standalone and API-only apps run outside the Shopify admin, unlike embedded apps. A standalone app serves its own UI, and an API-only app has no UI and runs as a server-side integration. Because they can't use  [ID tokens](/docs/apps/build/authentication-authorization/id-tokens) , they authenticate using the OAuth  [authorization code grant](/docs/apps/build/authentication-authorization/access-tokens#authorization-code-grant)  flow: redirect the merchant to Shopify, get their approval, and exchange a code for an access token.

Info

If your app only acts on stores in your own Shopify organization, use the  [client credentials grant](/docs/apps/build/authentication-authorization/client-credentials-grant)  instead. It skips the merchant authorization flow. To learn how authentication works for other common approaches, see  [About app authentication](/docs/apps/build/authentication-authorization) .

 **Info:**  

If your app only acts on stores in your own Shopify organization, use the  [client credentials grant](/docs/apps/build/authentication-authorization/client-credentials-grant)  instead. It skips the merchant authorization flow. To learn how authentication works for other common approaches, see  [About app authentication](/docs/apps/build/authentication-authorization) .

## [Anchor to What you'll learn](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#what-youll-learn) What you'll learn

In this tutorial, you'll learn how to do the following tasks:

- Redirect a merchant to Shopify's authorization page
- Validate the callback Shopify sends back to your app
- Exchange the authorization code for an offline access token
- Make authenticated GraphQL Admin API requests

## Requirements

 [App credentials](/docs/apps/build/authentication-authorization/manage-credentials) 

You have your app's client ID and client secret from the Dev Dashboard.

 [Redirect URI](/docs/apps/build/cli-for-apps/app-configuration#auth) 

You've added your app's redirect URI to your app's settings in the Dev Dashboard, or to the  `[auth]`  section of your  `shopify.app.toml` .

 [Access scopes](/docs/api/usage/access-scopes) 

You know which access scopes your app requires.

## Project

Language:Node.js Python Node.js [View on GitHub](https://github.com/Shopify/example-auth--authorization-code-grant) 

## [Anchor to Redirect to Shopify's authorization page](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#redirect-to-shopifys-authorization-page) Redirect to Shopify's authorization page

Send the merchant to Shopify to approve the access your app is asking for. Shopify presents a permissions prompt, and the merchant approves or denies it.

## [Anchor to Validate the callback](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#validate-the-callback) Validate the callback

After the merchant approves your app, Shopify redirects to your  `redirect_uri`  with an authorization code and several query parameters. Validate all of them before exchanging the code.

91https://your-app.example.com/callback?code={authorization_code}&hmac={hmac}&shop={shop}&state={nonce}&timestamp={timestamp}

## [Anchor to Exchange the code for an offline access token](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#exchange-the-code-for-an-offline-access-token) Exchange the code for an offline access token

Offline access tokens persist across sessions and aren't tied to a specific staff member. Exchange the authorization code for one by sending a  `POST`  request to Shopify's token endpoint.

## [Anchor to (Optional) Request an online access token](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#optional-request-an-online-access-token) (Optional) Request an online access token

Online access tokens are scoped to the staff member who authorized them, and they expire with that user's session. Request one when your app needs to respect an individual user's permission level or attribute actions to a specific user. Skip this step if an offline token is all your app needs.

A single authorization request returns one token type, so this step changes the flow you just built rather than adding to it. Your app can hold both, but each one needs its own record: key the offline token by shop, and each online token by shop and staff member. An online access token has no refresh token, so writing one into the offline token's record ends your app's background refresh. The samples on this page keep a single record per shop, so add a second store before you run this flow.

## [Anchor to Make authenticated API requests](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#make-authenticated-api-requests) Make authenticated API requests

Include the access token in the  `X-Shopify-Access-Token`  header on all GraphQL Admin API requests.

## [Anchor to Refresh the access token](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#refresh-the-access-token) Refresh the access token

Expiring offline access tokens come with a  `refresh_token` . Before the access token expires, exchange the refresh token for a new access token so your app keeps working without sending the merchant back through authorization.

## [Anchor to Tutorial complete!](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#tutorial-complete) Tutorial complete!

Your app now completes the authorization code grant and holds an access token it can use against Shopify APIs.

### [Anchor to Next steps](/docs/apps/build/authentication-authorization/authenticate-standalone-apps?lang=node#next-steps) Next steps

 [Manage your credentials

Find your client ID and secret, secure them, and rotate your client secret.

Manage your credentials

Find your client ID and secret, secure them, and rotate your client secret.](/docs/apps/build/authentication-authorization/manage-credentials)  [Manage your credentials

Find your client ID and secret, secure them, and rotate your client secret.](/docs/apps/build/authentication-authorization/manage-credentials)  [Query store data

Use your access token to query and mutate store data with the GraphQL Admin API.

Query store data

Use your access token to query and mutate store data with the GraphQL Admin API.](/docs/apps/build/graphql)  [Query store data

Use your access token to query and mutate store data with the GraphQL Admin API.](/docs/apps/build/graphql)  [Set up webhooks

Register webhooks for background tasks that run using your offline access token.

Set up webhooks

Register webhooks for background tasks that run using your offline access token.](/docs/apps/build/webhooks)  [Set up webhooks

Register webhooks for background tasks that run using your offline access token.](/docs/apps/build/webhooks)  [Manage access scopes

Change your declared scopes after launch, and request or revoke optional scopes dynamically.

Manage access scopes

Change your declared scopes after launch, and request or revoke optional scopes dynamically.](/docs/apps/build/authentication-authorization/manage-access-scopes)  [Manage access scopes

Change your declared scopes after launch, and request or revoke optional scopes dynamically.](/docs/apps/build/authentication-authorization/manage-access-scopes)  [Delegate API access

Give subsystems scoped, limited access to Shopify APIs without sharing your app's full credentials.

Delegate API access

Give subsystems scoped, limited access to Shopify APIs without sharing your app's full credentials.](/docs/apps/build/authentication-authorization/delegate-api-access)  [Delegate API access

Give subsystems scoped, limited access to Shopify APIs without sharing your app's full credentials.](/docs/apps/build/authentication-authorization/delegate-api-access)

## Sub-Topic: authenticated in the Shopify admin
> Source: https://shopify.dev/apps/auth/admin-app-access-tokens

# Generate access tokens for admin-created custom apps

Caution

You can no longer create new admin-created custom apps. Existing apps are unaffected and continue to work. For new apps, use  [Dev Dashboard](/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard)  or  [Shopify CLI](/docs/apps/build/cli-for-apps) .

 **Caution:**  

You can no longer create new admin-created custom apps. Existing apps are unaffected and continue to work. For new apps, use  [Dev Dashboard](/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard)  or  [Shopify CLI](/docs/apps/build/cli-for-apps) .

Admin-created custom apps are apps created directly in the Shopify admin, without going through the OAuth installation flow. Shopify pre-generates API access tokens when the merchant installs the app. There's no authorization code grant, no  `shopify.app.toml` , and no managed installation.

If you're maintaining an existing admin-created custom app, use this page to reference how to authenticate API requests, understand the limitations around credential rotation, and manage API scopes.

## [Anchor to Make authenticated requests](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps#make-authenticated-requests) Make authenticated requests

Your app's API access token is shown only once, when it's generated, so store it somewhere secure at that point. To see whether it's still available, go to  **Apps**  >  **Develop apps**  > [your app] >  **API credentials** . If the token is no longer retrievable, generate a new one. Use the token to authenticate requests to the GraphQL Admin API.

The following examples query the GraphQL Admin API to retrieve the first five products from a store.

Info

The following examples require the  `SHOP_TOKEN`  environment variable set to your Admin API access token with at least the  `read_products`  scope. Replace  `{shop}`  with your store's subdomain.

 **Info:**  

The following examples require the  `SHOP_TOKEN`  environment variable set to your Admin API access token with at least the  `read_products`  scope. Replace  `{shop}`  with your store's subdomain.

## cURL

 $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $curl -sX POST \ https://{shop}.myshopify.com/admin/api/2026-10/graphql.json \ -H 'Content-Type: application/json' \ -H "X-Shopify-Access-Token: ${SHOP_TOKEN}" \ -d @- <<EOF{ "query": "{ products(first: 5) { edges { node { id handle } } pageInfo { hasNextPage } } }"}EOF

You can pipe the response through  [`jq`](https://jqlang.org/)  to extract specific fields:

## cURL with jq

 $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $ $curl -sX POST \ https://{shop}.myshopify.com/admin/api/2026-10/graphql.json \ -H 'Content-Type: application/json' \ -H "X-Shopify-Access-Token: ${SHOP_TOKEN}" \ -d @- <<EOF | jq '.data.products.edges[].node | {id, handle}'{ "query": "{ products(first: 5) { edges { node { id handle } } pageInfo { hasNextPage } } }"}EOF

## [Anchor to Rotate or generate new credentials](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps#rotate-or-generate-new-credentials) Rotate or generate new credentials

You can't rotate the API key or secret for an admin-created custom app. To generate a new access token, uninstall and reinstall the app from the Shopify admin. The app itself stays intact: uninstalling removes it from the store, and reinstalling generates a new token. Your app's requests and webhooks are disrupted until you update your code with the new token.

Caution

Don't delete the app itself. Deleting removes the app configuration from the Shopify admin permanently, and you can't create a new admin-created custom app to replace it. If you need a new app, use  [Dev Dashboard](/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard)  to create one with a proper OAuth flow.

 **Caution:**  

Don't delete the app itself. Deleting removes the app configuration from the Shopify admin permanently, and you can't create a new admin-created custom app to replace it. If you need a new app, use  [Dev Dashboard](/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard)  to create one with a proper OAuth flow.

If you need to rotate access tokens for a custom storefront built with the Headless channel, see  [Rotate private access tokens](/docs/storefronts/headless/building-with-the-storefront-api/manage-headless-channels#rotate-private-access-tokens) .

## [Anchor to Change API scopes](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps#change-api-scopes) Change API scopes

Anyone with a  [staff or collaborator account](https://help.shopify.com/en/manual/your-account/staff-accounts/staff-permissions)  on a store can change what resources an admin-created custom app can access, provided they have the  **Manage and install apps and channels**  permission, the  **Develop apps**  permission, and the relevant permissions for the resource being changed.

The store owner can  [change staff or collaborator permissions](https://help.shopify.com/en/manual/your-account/staff-accounts/staff-permissions)  in the Shopify admin.

### [Anchor to Permissions required to assign scopes](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps#permissions-required-to-assign-scopes) Permissions required to assign scopes

The following table shows what store permissions a staff or collaborator account needs to assign  [Admin API access scopes](/docs/api/usage/access-scopes)  to an admin-created custom app. The account must also have the  **Develop apps**  permission in all cases.

| Admin API scope name | Permissions required |
| --- | --- |
| read_analytics | View store metrics |
| read_assigned_fulfillment_orders, write_assigned_fulfillment_orders | View or manage fulfillment orders |
| read_customer_merge, write_customer_merge | View or manage customer profile merges |
| read_customers, write_customers | View or manage customers, customer addresses, order history, and customer groups |
| read_discounts, write_discounts | View or manage automatic discounts and discount codes |
| read_draft_orders, write_draft_orders | View or manage orders created by app users on behalf of customers |
| read_files, write_files | View or manage files |
| read_fulfillments, write_fulfillments | View or manage fulfillment services |
| read_gdpr_data_request | View GDPR data requests |
| read_gift_cards, write_gift_cards | View or manage gift cards (Shopify Plus only) |
| read_inventory, write_inventory | View or manage inventory across multiple locations |
| read_legal_policies, write_legal_policies | View or manage a shop's legal policies |
| read_locations | View the geographic location of stores, headquarters, and warehouses |
| read_marketing_events, write_marketing_events | View or manage marketing events and engagement data |
| read_merchant_managed_fulfillment_orders, write_merchant_managed_fulfillment_orders | View or manage fulfillment orders assigned to merchant-managed locations |
| read_metaobject_definitions, write_metaobject_definitions | View or manage metaobject definitions |
| read_metaobjects, write_metaobjects | View or manage metaobject entries |
| read_online_store_navigation | View menus for display on the storefront |
| read_online_store_pages, write_online_store_pages | View or manage Online Store pages |
| read_order_edits, write_order_edits | View or manage edits to orders |
| read_orders, write_orders, read_all_orders | View or manage orders, transactions, fulfillments, and abandoned checkouts from the last 60 days, or view all past and future orders |
| read_price_rules, write_price_rules | View or manage conditional discounts |
| read_products, write_products | View or manage products, variants, and collections |
| read_product_listings, write_product_listings | View or manage product or collection listings |
| read_reports, write_reports | View or manage reports on the Reports page in the Shopify admin |
| read_resource_feedbacks, write_resource_feedbacks | View or manage the status of shops and resources |
| read_script_tags, write_script_tags | View or manage JavaScript code in storefront or order status pages |
| read_shipping, write_shipping | View or manage shipping carriers, countries, and provinces |
| read_shopify_payments_accounts | View Shopify Payments accounts |
| read_shopify_payments_bank_accounts | View bank accounts that can receive Shopify Payments payouts |
| read_shopify_payments_disputes | View Shopify Payments disputes raised by buyers |
| read_shopify_payments_payouts | View Shopify Payments payouts and the account's current balance |
| read_content, write_content | View or manage articles, blogs, comments, pages, and redirects |
| read_themes, write_themes | View or manage theme templates and assets |
| read_third_party_fulfillment_orders, write_third_party_fulfillment_orders | View or manage fulfillment orders assigned to a location managed by any fulfillment service |
| read_translations, write_translations | View or manage content that can be translated |

## [Anchor to Next steps](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps#next-steps) Next steps

- Learn how to  [configure a webhook](/docs/apps/build/webhooks/subscribe)  for your app and  [manage webhooks for different API versions](/docs/apps/build/webhooks/subscribe#versioning) .
- Explore the  [Webhooks references](/docs/api/webhooks)  and  [GraphQL Admin API](/docs/api/admin-graphql)  references.


## Sub-Topic: getting started with authentication
> Source: https://shopify.dev/apps/auth

# About app authentication

Shopify apps call the  [GraphQL Admin API](/docs/api/admin-graphql)  to read and write store data on behalf of merchants. Before your app can make those calls, it needs to authenticate: prove which app is calling, which merchant approved it, and what the app is allowed to do.

This section covers how that authentication works for apps calling the GraphQL Admin API, and points you to the setup path for the kind of app you're building. Other Shopify APIs issue their own token types and use their own headers, so if you're authenticating requests to the Storefront API or the Customer Account API, see  [Shopify API authentication](/docs/api/usage/authentication)  instead. You don't implement OAuth by hand for most apps.  [Shopify CLI](/docs/apps/build/cli-for-apps)  and the  [Shopify app templates](/docs/api/libraries-and-templates#app-templates)  handle the token flow for you.

## [Anchor to What you can do](/docs/apps/build/authentication-authorization#what-you-can-do) What you can do

- Call the GraphQL Admin API as an installed app, limited to the access scopes a merchant approved.
- Call the GraphQL Admin API directly from your app's frontend with  [Direct API access](/docs/api/app-home#direct-api-access) , where App Bridge authenticates each request.
- Run background jobs and scheduled tasks, and subscribe to webhooks, using an offline access token that persists across sessions.
- Attribute actions to a specific staff member and enforce per-user permissions using online access tokens.
- Give a subsystem limited, scoped access to Shopify APIs without sharing your app's full credentials, using  [delegate access tokens](/docs/apps/build/authentication-authorization/delegate-api-access) .

## [Anchor to How it works](/docs/apps/build/authentication-authorization#how-it-works) How it works

For any app with a backend of its own, authentication follows the same three steps:

1. Your app gets an  [access token](/docs/apps/build/authentication-authorization/access-tokens)  for the store it's calling.
2. Your app sends the token in the  `X-Shopify-Access-Token`  header on every GraphQL Admin API request.
3. Shopify returns the data the token's  [access scopes](/docs/apps/build/authentication-authorization/manage-access-scopes)  allow, or an error if the request doesn't meet an access requirement.

What differs is how your app gets that token:

- Most apps get one after a merchant installs the app and approves its scopes.
- After installation and scope approval, an app can request tokens for later server-side work with client credentials (including a  [signed client assertion](/docs/apps/build/authentication-authorization/access-tokens#authenticate-with-a-client-assertion) ) without another merchant session or approval step. This works for stores in your organization, and for any store that has installed an app with public distribution that uses a client assertion.

Extension-only apps have no backend and never hold a token. Shopify authenticates their requests through  [Direct API access](/docs/api/app-home#direct-api-access) .

Choosing an approach maps each option to its setup guide.

## [Anchor to Access requirements](/docs/apps/build/authentication-authorization#access-requirements) Access requirements

Every GraphQL Admin API request is checked against a few different requirements. Most apps only need the first two:

- **A valid access token** : Your app holds a token for the store it's calling and sends it in the  `X-Shopify-Access-Token`  header.
- **The access scope the field requires** : Each field and mutation names the scope that grants it, and your app's token carries the scopes the merchant approved. Refer to  [access scopes](/docs/api/usage/access-scopes) .
- **For a small number of scopes, Shopify's approval** : Shopify grants some access scopes to individual apps rather than to every app that declares them.  [Access scopes](/docs/api/usage/access-scopes#requesting-specific-permissions)  lists which ones and how to request each.
- **An online access token's staff permissions** : Apps get  [offline access tokens](/docs/apps/build/authentication-authorization/access-tokens#offline-access-tokens)  by default, but if your app requests an  [online access token](/docs/apps/build/authentication-authorization/access-tokens#online-access-tokens)  instead, it's narrowed to what the staff member who authorized it can do, so a request can be refused even when your app holds the scope.
- **Approval to use protected customer data** : Fields that return a customer's personal data need a separate approval if your app is public. A custom app has that access automatically, though an admin-created custom app's access to name, address, phone, and email fields varies by plan. Refer to  [protected customer data](/docs/apps/launch/protected-customer-data) .

## [Anchor to Key terminology](/docs/apps/build/authentication-authorization#key-terminology) Key terminology

These terms come up across Shopify's authentication flows and throughout the rest of this section.

### [Anchor to Authentication and authorization](/docs/apps/build/authentication-authorization#authentication-and-authorization) Authentication and authorization

Authentication proves which identity is making a request. Authorization determines what that identity is allowed to do. On each API request, the access token does both: it identifies your app, and its  [access scopes](/docs/apps/build/authentication-authorization/manage-access-scopes)  determine what it can access.

Some flows authenticate a user first. For example, embedded apps validate an  [ID token](/docs/apps/build/authentication-authorization/id-tokens) , then exchange it for an access token.

### [Anchor to Access token](/docs/apps/build/authentication-authorization#access-token) Access token

The credential your code sends on each GraphQL Admin API request, in the  `X-Shopify-Access-Token`  header.  **Online**  or  **offline**  describes a token's lifetime: online tokens last as long as a staff member's session, while offline tokens persist across sessions. See  [access tokens](/docs/apps/build/authentication-authorization/access-tokens) .

### [Anchor to ID token](/docs/apps/build/authentication-authorization#id-token) ID token

A short-lived JWT that proves a request comes from an authenticated Shopify user.  [App Bridge](/docs/api/app-home)  issues one to the frontend of an app running inside the Shopify admin, and your app usually exchanges it for an access token rather than sending it to an API. App Bridge 2.0 and older documentation call the same credential a session token. See  [ID tokens](/docs/apps/build/authentication-authorization/id-tokens) , or  [Set up session tokens with App Bridge 2.0](/docs/apps/build/authentication-authorization/legacy/app-bridge-2-setup)  if that's the version your app uses.

### [Anchor to Grant](/docs/apps/build/authentication-authorization#grant) Grant

The OAuth flow your app uses to get an access token. Shopify supports three, and which one applies depends on where your app runs and whose stores it acts on:

- **[Token exchange](/docs/apps/build/authentication-authorization/access-tokens#token-exchange-grant)** , for apps that run inside the Shopify admin. Your app exchanges an ID token for an access token without redirecting the merchant.
- **[Authorization code grant](/docs/apps/build/authentication-authorization/access-tokens#authorization-code-grant)** , for apps that run outside the Shopify admin. The merchant is redirected to Shopify to approve access, then back to your app with a code that your app exchanges for an access token.
- **[Client credentials grant](/docs/apps/build/authentication-authorization/access-tokens#client-credentials-grant)** , for server-side work without a merchant session. Apps can authenticate with a client secret for stores in their organization, or with a client assertion signed with their private key. Public-distribution apps using a client assertion can request tokens for any store that has installed them.

Choosing an approach maps each grant to its setup guide.

### [Anchor to Shopify managed installation](/docs/apps/build/authentication-authorization#shopify-managed-installation) Shopify managed installation

The installation method where Shopify installs your app and updates its access scopes without calling your app. You declare the scopes your app needs in its  `shopify.app.toml`  configuration file and push it to Shopify, which then handles the merchant's approval. Apps built with Shopify CLI use managed installation by default, which is why they don't implement the authorization code grant.

### [Anchor to Client ID and client secret](/docs/apps/build/authentication-authorization#client-id-and-client-secret) Client ID and client secret

The credentials that identify your app, issued when you create it. The client ID is public. The client secret isn't: it proves a request comes from your app, so keep it server-side and never ship it in client code. Don't confuse them with the client credentials grant, which is one of the flows that uses them. See  [manage your app credentials](/docs/apps/build/authentication-authorization/manage-credentials) .

### [Anchor to Access scopes](/docs/apps/build/authentication-authorization#access-scopes) Access scopes

A named unit of access that a merchant grants your app, such as  `read_products`  or  `write_orders` . The scopes on an access token determine what that token can read and write. Any scope that writes a resource also grants read access to it, so request the write scope only when your app needs both. Scopes are one of several access requirements a request has to meet. See  [manage access scopes](/docs/apps/build/authentication-authorization/manage-access-scopes) .

## [Anchor to Choosing an approach](/docs/apps/build/authentication-authorization#choosing-an-approach) Choosing an approach

Most apps are embedded, meaning they run inside the Shopify admin, and building one with Shopify CLI is the recommended path. Apps that aren't embedded might run outside the Shopify admin, or act only on stores in your own organization.

How your app gets an  [access token](/docs/apps/build/authentication-authorization/access-tokens)  depends on where it runs and whose stores it acts on, and an app with no backend of its own doesn't get one at all:

| If your app | How it authenticates | Set it up |
| --- | --- | --- |
| Runs in the Shopify admin and is built with Shopify CLI | Token exchange | Authentication for apps built with Shopify CLI |
| Runs in the Shopify admin but doesn't use a Shopify app template | Token exchange | Authenticate an embedded app without a template |
| Runs outside the Shopify admin | Authorization code grant | Authenticate a standalone or API-only app |
| Is a server-side integration that acts on your own stores | Client credentials grant | Authenticate an app for stores in your organization |
| Needs to act on stores that have installed it, without a merchant session, such as for background jobs | Client credentials grant with a client assertion | Get application-only access tokens for installed stores |
| Is extension-only, with no backend of its own | Direct API access, so there's no token to get | Build an extension-only app |

The client credentials grant works only for stores in your organization, unless your app has public distribution and authenticates with a client assertion. Every other option works on any merchant's stores, including your clients'. For information about getting your app onto stores outside your own organization, see  [About app distribution](/docs/apps/launch/distribution) .

Whichever token route you use, your app sends the token it ends up with in the same header, and the GraphQL Admin API calls it makes with that token are the same.

If you're building without a template, Shopify's  [official libraries](/docs/api/libraries-and-templates#official-api-libraries)  can handle token exchange, request verification, and GraphQL Admin API calls for you.

InfoThe table above doesn't cover apps created directly in the Shopify admin, which Shopify pre-generates an access token for when the merchant installs the app. You can no longer create these apps, but if you maintain one, see  [Generate access tokens for admin-created custom apps](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps) . **Info:**  The table above doesn't cover apps created directly in the Shopify admin, which Shopify pre-generates an access token for when the merchant installs the app. You can no longer create these apps, but if you maintain one, see  [Generate access tokens for admin-created custom apps](/docs/apps/build/authentication-authorization/legacy/admin-custom-apps) .


## Sub-Topic: StorefrontAccessToken
> Source: https://shopify.dev/docs/api/admin-rest/latest/resources/storefrontaccesstoken

The REST Admin API is a legacy API as of October 1, 2024. Starting April 1, 2025, all new public apps must be built exclusively with the  [GraphQL Admin API](/docs/api/admin-graphql) .

Choose a version:unstable 2027-01 release candidate2026-10 latest2026-07 2026-04 2026-01 2026-10latest

# StorefrontAccessToken

You can use the StorefrontAccessToken resource to generate storefront access tokens. Storefront access tokens are
 used to delegate unauthenticated access scopes to clients that need to access the unautheticated Storefront API. A sales channel
 can generate a storefront access token and then pass it to a consuming client, such as JavaScript or a mobile application.

Note
 
 

Storefront access tokens are allocated on a per shop basis, and an application can have a maximum of 100 active Storefront access tokens per shop.

 **Note:**  
 
 

Storefront access tokens are allocated on a per shop basis, and an application can have a maximum of 100 active Storefront access tokens per shop.

A storefront access token inherits all of the  [unauthenticated access
scopes](/docs/storefront-api/access-scopes)  from the app that creates it. If the app has not been granted any unauthenticated access scopes, then
creating the storefront access token will fail.

#

## Endpoints

- [post/admin/api/latest/storefront_access_tokens.json](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#post-storefront-access-tokens) Creates a new StorefrontAccessToken [storefrontAccessTokenCreate](/docs/api/admin-graphql/latest/mutations/storefrontAccessTokenCreate?example=creates-a-new-storefrontaccesstoken)
- [get/admin/api/latest/storefront_access_tokens.json](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#get-storefront-access-tokens) Retrieves a list of storefront access tokens that have been issued [shop](/docs/api/admin-graphql/latest/queries/shop?example=retrieves-a-list-of-storefront-access-tokens-that-have-been-issued)
- [del/admin/api/latest/storefront_access_tokens/{storefront_access_token_id}.json](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#delete-storefront-access-tokens-storefront-access-token-id) Deletes an existing storefront access token [storefrontAccessTokenDelete](/docs/api/admin-graphql/latest/mutations/storefrontAccessTokenDelete?example=deletes-an-existing-storefront-access-token)

 [Anchor to](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#resource-object) 

## The StorefrontAccessToken resource

 [Anchor to](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#resource-object-properties) 

### Properties

idread-only **read-only** -> [id](/docs/api/admin-graphql/latest/objects/StorefrontAccessToken#field-StorefrontAccessToken.fields.id) 

Unique  `id`  that identifies a token and is used to perform operations on it.

access_tokenread-only **read-only** -> [accessToken](/docs/api/admin-graphql/latest/objects/StorefrontAccessToken#field-StorefrontAccessToken.fields.accessToken) 

The issued public access token.

access_scoperead-only **read-only** -> [accessScopes](/docs/api/admin-graphql/latest/objects/StorefrontAccessToken#field-StorefrontAccessToken.fields.accessScopes) 

An application-dependant, comma separated list of permissions associated with the token.

created_atread-only **read-only** -> [createdAt](/docs/api/admin-graphql/latest/objects/StorefrontAccessToken#field-StorefrontAccessToken.fields.createdAt) 

The date and time when the public access token was created. The API returns this value in  [ISO 8601 format](//en.wikipedia.org/wiki/ISO_8601) .

title-> [title](/docs/api/admin-graphql/latest/objects/StorefrontAccessToken#field-StorefrontAccessToken.fields.title) 

An arbitrary title for each token determined by the developer/application, used for reference purposes.

Note
 
 

No constraint on uniqueness.

  **Note:**  
 
 

No constraint on uniqueness.

 

{}

## The StorefrontAccessToken resource

991234567891011121314151617{ "id": { "id": 1053727709 }, "access_token": { "access_token": "{token}" }, "access_scope": { "access_scope": "unauthenticated_read_product_listings" }, "created_at": { "created_at": "2016-11-10T15:15:47-05:00" }, "title": { "title": "Test" }}

## [Anchor to POST request, Creates a new StorefrontAccessToken](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#post-storefront-access-tokens) postCreates a new StorefrontAccessToken

 [storefrontAccessTokenCreate](/docs/api/admin-graphql/latest/mutations/storefrontAccessTokenCreate?example=creates-a-new-storefrontaccesstoken) 

Creates a new storefront access token

### [Anchor to Parameters of Creates a new StorefrontAccessToken](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#post-storefront-access-tokens-parameters) Parameters

api_versionstring **string** required **required** 

### [Anchor to post-storefront-access-tokens-examples](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#post-storefront-access-tokens-examples) Examples

Create a new storefront access token

Request bodystorefront_access_tokenStorefront_access_token resource **Storefront_access_token resource** Show storefront_access_token propertiesstorefront_access_token.title:"Test"-> [title](/docs/api/admin-graphql/latest/input-objects/StorefrontAccessTokenInput#fields-title) 

An arbitrary title for each token determined by the developer/application, used for reference purposes.

Note
 
 

No constraint on uniqueness.

  **Note:**  
 
 

No constraint on uniqueness.

 

Creating a token after exceeding the limit fails

Request bodystorefront_access_tokenStorefront_access_token resource **Storefront_access_token resource** Show storefront_access_token propertiesstorefront_access_token.title:"Token"-> [title](/docs/api/admin-graphql/latest/input-objects/StorefrontAccessTokenInput#fields-title) 

An arbitrary title for each token determined by the developer/application, used for reference purposes.

Note
 
 

No constraint on uniqueness.

  **Note:**  
 
 

No constraint on uniqueness.

 

Generating a token for an app that lacks required unauthenticated scopes fails

Request bodystorefront_access_tokenStorefront_access_token resource **Storefront_access_token resource** Show storefront_access_token propertiesstorefront_access_token.title:"Test"-> [title](/docs/api/admin-graphql/latest/input-objects/StorefrontAccessTokenInput#fields-title) 

An arbitrary title for each token determined by the developer/application, used for reference purposes.

Note
 
 

No constraint on uniqueness.

  **Note:**  
 
 

No constraint on uniqueness.

 

post

## /admin/api/2026-10/storefront_access_tokens.json

91234curl -d '{"storefront_access_token":{"title":"Test"}}' \-X POST "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \-H "X-Shopify-Access-Token: {access_token}" \-H "Content-Type: application/json"{}

## Response

JSON991234567891011HTTP/1.1 200 OK{ "storefront_access_token": { "access_token": "{token}", "access_scope": "unauthenticated_read_product_listings", "created_at": "2026-10-01T10:21:06-04:00", "id": 1003303990, "admin_graphql_api_id": "gid://shopify/StorefrontAccessToken/1003303990", "title": "Test" }}

### examples

- #### Create a new storefront access token

##### 

```curl
curl -d '{"storefront_access_token":{"title":"Test"}}' \
-X POST "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \
-H "X-Shopify-Access-Token: {access_token}" \
-H "Content-Type: application/json"
```

##### 

```remix
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
);
```

##### 

```ruby
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
    test_session,
);
```

##### 

```node
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
);
```

#### response

```json
HTTP/1.1 200 OK{"storefront_access_token":{"access_token":"{token}","access_scope":"unauthenticated_read_product_listings","created_at":"2026-10-01T10:21:06-04:00","id":1003303990,"admin_graphql_api_id":"gid://shopify/StorefrontAccessToken/1003303990","title":"Test"}}
```
- #### Creating a token after exceeding the limit fails

##### 

```curl
curl -d '{"storefront_access_token":{"title":"Token"}}' \
-X POST "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \
-H "X-Shopify-Access-Token: {access_token}" \
-H "Content-Type: application/json"
```

##### 

```remix
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Token";
$storefront_access_token->post(
);
```

##### 

```ruby
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Token";
$storefront_access_token->post(
    test_session,
);
```

##### 

```node
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Token";
$storefront_access_token->post(
);
```

#### response

```json
HTTP/1.1 400 Bad Request{"errors":["Api permission exceeds public access token limit of: 100"]}
```
- #### Generating a token for an app that lacks required unauthenticated scopes fails

##### 

```curl
curl -d '{"storefront_access_token":{"title":"Test"}}' \
-X POST "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \
-H "X-Shopify-Access-Token: {access_token}" \
-H "Content-Type: application/json"
```

##### 

```remix
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
);
```

##### 

```ruby
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
    test_session,
);
```

##### 

```node
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token = new StorefrontAccessToken($this->test_session);
$storefront_access_token->title = "Test";
$storefront_access_token->post(
);
```

#### response

```json
HTTP/1.1 403 Forbidden{"errors":"App must be extendable to create a storefront access token."}
```

## [Anchor to GET request, Retrieves a list of storefront access tokens that have been issued](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#get-storefront-access-tokens) getRetrieves a list of storefront access tokens that have been issued

 [shop](/docs/api/admin-graphql/latest/queries/shop?example=retrieves-a-list-of-storefront-access-tokens-that-have-been-issued) 

Retrieves a list of storefront access tokens that have been issued

### [Anchor to Parameters of Retrieves a list of storefront access tokens that have been issued](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#get-storefront-access-tokens-parameters) Parameters

api_versionstring **string** required **required** 

### [Anchor to get-storefront-access-tokens-examples](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#get-storefront-access-tokens-examples) Examples

Retrieve a list of storefront access tokens that have been issued

get

## /admin/api/2026-10/storefront_access_tokens.json

912curl -X GET "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \-H "X-Shopify-Access-Token: {access_token}"{}

## Response

JSON9912345678910111213HTTP/1.1 200 OK{ "storefront_access_tokens": [ { "access_token": "{token}", "access_scope": "unauthenticated_read_product_listings", "created_at": "2026-10-01T10:20:57-04:00", "id": 755357713, "admin_graphql_api_id": "gid://shopify/StorefrontAccessToken/755357713", "title": "API Client Extension" } ]}

### examples

- #### Retrieve a list of storefront access tokens that have been issued

##### 

```curl
curl -X GET "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens.json" \
-H "X-Shopify-Access-Token: {access_token}"
```

##### 

```remix
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$response = admin.rest.resources.StorefrontAccessToken::all(
);
```

##### 

```ruby
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$response = StorefrontAccessToken::all(
);
```

##### 

```node
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$response = StorefrontAccessToken::all(
);
```

#### response

```json
HTTP/1.1 200 OK{"storefront_access_tokens":[{"access_token":"{token}","access_scope":"unauthenticated_read_product_listings","created_at":"2026-10-01T10:20:57-04:00","id":755357713,"admin_graphql_api_id":"gid://shopify/StorefrontAccessToken/755357713","title":"API Client Extension"}]}
```

## [Anchor to DELETE request, Deletes an existing storefront access token](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#delete-storefront-access-tokens-storefront-access-token-id) delDeletes an existing storefront access token

 [storefrontAccessTokenDelete](/docs/api/admin-graphql/latest/mutations/storefrontAccessTokenDelete?example=deletes-an-existing-storefront-access-token) 

Deletes an existing storefront access token

### [Anchor to Parameters of Deletes an existing storefront access token](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#delete-storefront-access-tokens-storefront-access-token-id-parameters) Parameters

api_versionstring **string** required **required** storefront_access_token_idstring **string** required **required** 

### [Anchor to delete-storefront-access-tokens-storefront-access-token-id-examples](/docs/api/admin-rest/latest/resources/storefrontaccesstoken#delete-storefront-access-tokens-storefront-access-token-id-examples) Examples

Delete an existing storefront access token

Path parametersstorefront_access_token_id=755357713string **string** required **required** del

## /admin/api/2026-10/storefront_access_tokens/755357713.json

912curl -X DELETE "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens/755357713.json" \-H "X-Shopify-Access-Token: {access_token}"{}

## Response

JSON91HTTP/1.1 200 OK

### examples

- #### Delete an existing storefront access token

##### 

```curl
curl -X DELETE "https://your-development-store.myshopify.com/admin/api/2026-10/storefront_access_tokens/755357713.json" \
-H "X-Shopify-Access-Token: {access_token}"
```

##### 

```remix
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token->delete(
    755357713,
);
```

##### 

```ruby
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token->delete(
    755357713,
);
```

##### 

```node
use Shopify\Rest\Admin2026_10\StorefrontAccessToken;
use Shopify\Utils;

$this->test_session = Utils::loadCurrentSession(
    $requestHeaders,
    $requestCookies,
    $isOnline
);

$storefront_access_token->delete(
    755357713,
);
```

#### response

```json
HTTP/1.1 200 OK
```