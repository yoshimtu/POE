"""Firebase client authentication. User tokens stay local to each installation."""
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY = 'AIzaSyCTuWg6caoca6QUmh08hKhqzDBJzk0B0I4'
DATABASE_URL = 'https://waymark-2e21e-default-rtdb.firebaseio.com'


def _post_json(url, body):
    request = Request(url, data=json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read(1_000_000))
    except HTTPError as exc:
        raise ValueError('Firebase authentication failed (HTTP %s).' % exc.code) from None


def anonymous_sign_in():
    result = _post_json('https://identitytoolkit.googleapis.com/v1/accounts:signUp?key='+API_KEY,
                        {'returnSecureToken': True})
    return {'uid': result['localId'], 'id_token': result['idToken'],
            'refresh_token': result['refreshToken'],
            'expires_at': time.time() + int(result['expiresIn']) - 60}
