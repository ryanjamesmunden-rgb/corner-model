# Auth-Gated App Testing Playbook (Emergent Google Auth)

## Step 1: Create Test User & Session (mongosh)
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({ user_id: userId, email: 'test.user.'+Date.now()+'@example.com', name: 'Test User', picture: 'https://via.placeholder.com/150', created_at: new Date() });
db.user_sessions.insertOne({ user_id: userId, session_token: sessionToken, expires_at: new Date(Date.now()+7*24*60*60*1000).toISOString(), created_at: new Date().toISOString() });
print('Session token: ' + sessionToken);
"
```

## Step 2: Test Backend API
```
curl -X GET "$URL/api/auth/me" -H "Authorization: Bearer <TOKEN>"
curl -X GET "$URL/api/leagues" -H "Authorization: Bearer <TOKEN>"
curl -X GET "$URL/api/scanner?league_id=all&min_edge=0" -H "Authorization: Bearer <TOKEN>"
```

## Step 3: Browser Testing
```
await page.context.add_cookies([{ "name":"session_token","value":"<TOKEN>","domain":"<host>","path":"/","httpOnly":true,"secure":true,"sameSite":"None" }])
await page.goto("<URL>/scanner")
```

## Checklist
- users doc has user_id (custom); sessions user_id matches
- all queries use {"_id":0}
- /api/auth/me returns user data; protected routes load without redirect
