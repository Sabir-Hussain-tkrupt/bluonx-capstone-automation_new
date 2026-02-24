"""
FastAPI JWT Authentication Utilities (Stub)
============================================
Full implementation: Task 2.6

This module will:
1. Validate Supabase JWTs on incoming requests
2. Extract user_id from the token
3. Provide a dependency for protected endpoints
4. Use the Supabase JWT secret to verify signatures

Architecture:
  - All writes go through FastAPI using service_role key (bypasses RLS)
  - JWT validation confirms the caller is a legitimate authenticated user
  - User role/permissions checked against public.users table
"""

# TODO (Task 2.6): Implement the following
#
# from fastapi import Depends, HTTPException, status
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# import jwt  # PyJWT library
#
# SUPABASE_JWT_SECRET = settings.SUPABASE_JWT_SECRET  # from env
#
# async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
#     """
#     Dependency that validates the JWT and returns the user_id.
#
#     Usage:
#       @router.get("/vendors")
#       async def list_vendors(user_id: str = Depends(get_current_user)):
#           ...
#     """
#     token = credentials.credentials
#     payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
#     return payload["sub"]  # sub = user UUID
#
# async def require_admin(user_id: str = Depends(get_current_user)):
#     """
#     Dependency that requires the admin role.
#     Queries public.users to check role.
#     """
#     # Query public.users where id = user_id and role = 'admin'
#     pass