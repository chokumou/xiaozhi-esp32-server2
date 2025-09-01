from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import os
import time
import datetime

try:
    import jwt
except Exception:
    jwt = None

router = APIRouter()


class ProvisionRequest(BaseModel):
    device_id: str


class ProvisionResponse(BaseModel):
    jwt: str


@router.post('/provision', response_model=ProvisionResponse)
async def provision_device(req: ProvisionRequest, request: Request):
    """Issue a JWT for the given device_id.

    This endpoint MUST be protected in production (admin API key / auth). Here we
    create an HS256 JWT signed with JWT_SECRET_KEY for short-term device use.
    Replace with Supabase-based issuance for full production integration.
    """
    # Simple protection: require an admin header (to be replaced by proper auth)
    admin_key = request.headers.get('x-admin-key') or os.getenv('PROVISION_ADMIN_KEY')
    if not admin_key:
        raise HTTPException(status_code=401, detail='Provision admin key missing')

    # Create JWT
    secret = os.getenv('JWT_SECRET_KEY')
    if not secret:
        raise HTTPException(status_code=500, detail='Server not configured for JWT issuance')

    now = int(time.time())
    payload = {
        'sub': req.device_id,
        'iat': now,
        'exp': now + 60 * 60 * 24,  # 24 hours
        'iss': 'nekota-provision',
    }

    if jwt is None:
        raise HTTPException(status_code=500, detail='jwt library not available on server')

    token = jwt.encode(payload, secret, algorithm='HS256')
    return ProvisionResponse(jwt=token)


