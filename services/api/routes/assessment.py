import uuid
from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from ..models import Assessment
from ..db import get_db
from ..security import current_user
from ..services.learning import emit
router=APIRouter(prefix='/assessment',tags=['Assessment'])
QUESTIONS=[
 {'prompt':'Choose a greeting.','choices':['Hello','Goodbye','Yesterday'],'answer':'Hello','skill':'vocabulary','level':'A1'},
 {'prompt':'She ___ a student.','choices':['am','are','is'],'answer':'is','skill':'grammar','level':'A1'},
 {'prompt':'Alex lives in London. Where does Alex live?','choices':['Tashkent','London','Paris'],'answer':'London','skill':'reading','level':'A1'},
 {'prompt':'Yesterday we ___ to a cafe.','choices':['go','went','going'],'answer':'went','skill':'grammar','level':'A2'},
 {'prompt':'I have never been to London. Has the speaker visited London?','choices':['Yes','No','Every week'],'answer':'No','skill':'reading','level':'A2'},
 {'prompt':'If I have time, I ___ you.','choices':['will call','would called','calling'],'answer':'will call','skill':'grammar','level':'A2'}]
@router.get('')
def questions(user=Depends(current_user)):
 return {'questions':[{k:v for k,v in q.items() if k!='answer'} for q in QUESTIONS],'note':'Короткая предварительная оценка чтения, грамматики и словаря. Аудирование и речь не проверяются; это не сертификат CEFR.'}
class Submission(BaseModel):
 answers:list[str]=Field(min_length=6,max_length=6)
@router.post('')
def evaluate(body:Submission,user=Depends(current_user),db=Depends(get_db)):
 correct=[a==q['answer'] for a,q in zip(body.answers,QUESTIONS)]
 level='A2 practice' if all(correct[:3]) and sum(correct)>=5 else 'A1 practice'
 gaps=list({q['skill'] for q,ok in zip(QUESTIONS,correct) if not ok})
 result={'level':level,'correct':sum(correct),'total':6,'gaps':gaps,'note':'Ориентир для выбора упражнений. Устная речь и аудирование не проверены; высокий CEFR не присваивается.'}
 db.add(Assessment(id=str(uuid.uuid4()),user_id=user.id,answers=body.answers,result=result))
 user.settings={**user.settings,'assessment':result}
 emit(db,user.id,'assessment_completed',level=level)
 return result
