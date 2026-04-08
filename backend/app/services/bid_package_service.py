"""Stub for test collection — will be replaced by real implementation."""

class BidPackageValidationError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

async def create_bid_package_with_invitations(**kwargs):
    raise NotImplementedError("Not yet implemented")

async def resend_invitation(**kwargs):
    raise NotImplementedError("Not yet implemented")
