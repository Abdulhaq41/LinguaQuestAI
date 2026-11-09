from typing import Literal
import uuid
from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from ..db import get_db
from ..security import current_user
from ..services.learning import emit
router=APIRouter(prefix='/events',tags=['Telemetry'])
class Telemetry(BaseModel):
    kind:Literal['app_opened','paywall_viewed','plan_selected']
    plan:Literal['START','PRO','ULTRA'] | None=None
@router.post('')
def capture(body:Telemetry,user=Depends(current_user),db=Depends(get_db)):
    # Client telemetry is never financial or entitlement evidence.
    emit(db,user.id,body.kind,plan=body.plan)
    return {'ok':True}
