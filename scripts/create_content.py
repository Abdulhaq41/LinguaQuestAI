"""Author-reviewed seed content. No generation at runtime; answers remain server-side."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'content'/'lessons'
def ex(kind,prompt,answer,explanation,choices=None,audio=None):
    item={'type':kind,'prompt':prompt,'answers':answer if isinstance(answer,list) else [answer],'explanation':explanation}
    if choices:item['choices']=choices
    if audio:item['audio']=audio
    return item
lessons=[
{'id':'first-hello','title':'Первое знакомство','level':'A1','chapter':'01 · Начало приключения','description':'Поздоровайтесь, представьтесь и познакомьтесь с новым другом.','minutes':5,'xp':50,'free':True,'grammar':'I am → I’m. Для вопроса меняем порядок: Are you…?','vocabulary':[{'word':'hello','ru':'привет','uz':'salom'},{'word':'name','ru':'имя','uz':'ism'},{'word':'friend','ru':'друг','uz':'doʻst'},{'word':'nice','ru':'приятный','uz':'yoqimli'}],'examples':['Hello! My name is Alex.','I am a student. → I’m a student.','Nice to meet you!'],'exercises':[
ex('choice','Как поздороваться по-английски?','Hello','Hello — нейтральное приветствие. Goodbye — прощание.',['Goodbye','Hello','Thanks']),
ex('gap','My name ___ Lexi.','is','Сочетание my name требует is: My name is Lexi.',['are','am','is']),
ex('order','Составьте фразу: «Я студент».','I am a student','I + am + a student. Перед профессией или ролью в единственном числе нужен a.',['student','a','I','am']),
ex('text','Переведите: «Меня зовут Алекс».',['My name is Alex','I am Alex',"I'm Alex"],'И My name is Alex, и I am Alex подходят для знакомства.'),
ex('choice','Nice to meet you! — Выберите вежливый ответ.','Nice to meet you too!','Too в конце означает «тоже».',['Good night!','Nice to meet you too!','I am a book.']),
ex('correction','Исправьте: I is a student.',['I am a student',"I'm a student"],'С I используется am, а не is.') ]},
{'id':'cafe','title':'Кофе и добрые слова','level':'A1','chapter':'01 · Начало приключения','description':'Закажите напиток в кафе и вежливо поблагодарите.','minutes':5,'xp':60,'free':False,'grammar':'I would like… — вежливая просьба. Сокращение: I’d like…','vocabulary':[{'word':'coffee','ru':'кофе','uz':'qahva'},{'word':'tea','ru':'чай','uz':'choy'},{'word':'please','ru':'пожалуйста','uz':'iltimos'}],'examples':['I would like a coffee, please.','Can I have some water?','Thank you!'],'exercises':[
ex('choice','Выберите вежливый заказ.','I would like a tea, please.','I would like — вежливая форма просьбы.',['Give tea now!','I would like a tea, please.','Tea me!']),
ex('gap','Can I ___ some water, please?','have','Can I have…? — Можно мне…?',['has','having','have']),
ex('order','Составьте заказ.','A coffee please','В контексте заказа a coffee — одна порция кофе.',['please','coffee','A']),
ex('text','Переведите: «Спасибо».',['Thank you','Thanks'],'Thank you — нейтрально, Thanks — более неформально.'),
ex('correction','Исправьте: I would likes a coffee.','I would like a coffee','После would используется начальная форма like.') ]},
{'id':'daily-routine','title':'Мой обычный день','level':'A1','chapter':'02 · Жизнь в городе','description':'Расскажите, где живёте и чем занимаетесь каждый день.','minutes':6,'xp':60,'free':False,'grammar':'Present Simple: I work, she works. В отрицании: I do not work; she does not work.','vocabulary':[{'word':'work','ru':'работать','uz':'ishlamoq'},{'word':'live','ru':'жить','uz':'yashamoq'},{'word':'study','ru':'учиться','uz':'oʻqimoq'}],'examples':['I live in Tashkent.','She works in London.','He does not work on Sunday.'],'exercises':[
ex('gap','She ___ English every day.','studies','После согласной + y: study → studies в 3-м лице.',['study','studies','studying']),
ex('choice','Как сказать «Я живу в Ташкенте»?','I live in Tashkent.','Для города используем in.',['I live at Tashkent.','I lives in Tashkent.','I live in Tashkent.']),
ex('correction','Исправьте: He do not work.',['He does not work',"He doesn't work"],'He → does not; основной глагол work остаётся без -s.'),
ex('order','Составьте предложение.','I study English every day','Every day — каждый день.',['English','day','I','every','study']),
ex('text','Переведите: «Она работает».',['She works','She does work'],'She works — обычное утверждение в Present Simple.') ]},
{'id':'directions','title':'Найти дорогу','level':'A1','chapter':'02 · Жизнь в городе','description':'Спросите, где станция, и разберитесь с простыми указаниями.','minutes':5,'xp':60,'free':False,'grammar':'Where is…? — Где находится…? Go straight. Turn left/right.','vocabulary':[{'word':'left','ru':'налево','uz':'chapga'},{'word':'right','ru':'направо','uz':'oʻngga'},{'word':'station','ru':'станция','uz':'bekat'}],'examples':['Excuse me, where is the station?','Go straight and turn left.','The cafe is next to the hotel.'],'exercises':[
ex('choice','Turn left означает…','Поверните налево','Left — лево, right — право.',['Идите прямо','Поверните налево','Остановитесь']),
ex('gap','Where ___ the station?','is','The station — единственное число, поэтому is.',['are','am','is']),
ex('order','Составьте вопрос.','Where is the hotel','Порядок слов: Where + is + the hotel.',['hotel','the','Where','is']),
ex('text','Переведите: «Идите прямо».','Go straight','Go straight — идите прямо.'),
ex('choice','The cafe is next to the hotel. Где кафе?','Рядом с отелем','Next to означает «рядом с».',['Внутри отеля','Рядом с отелем','За городом']) ]},
{'id':'yesterday','title':'Вчера в Лондоне','level':'A2','chapter':'03 · Новые истории','description':'Расскажите о событиях прошедшего дня.','minutes':6,'xp':70,'free':False,'grammar':'Past Simple: visit → visited. Неправильный go → went. После did/did not — начальная форма.','vocabulary':[{'word':'yesterday','ru':'вчера','uz':'kecha'},{'word':'visited','ru':'посетил','uz':'tashrif buyurdi'},{'word':'went','ru':'пошёл','uz':'bordi'}],'examples':['I visited London yesterday.','We went to a cafe.','Did you enjoy the trip?'],'exercises':[
ex('gap','Yesterday we ___ to a cafe.','went','Прошедшая форма go — went.',['go','went','going']),
ex('correction','Исправьте: Did you visited London?','Did you visit London','После did используем visit, а не visited.'),
ex('choice','I did not buy a ticket. Что произошло?','Я не купил билет','Did not buy — отрицание в прошедшем времени.',['Я куплю билет','Я не купил билет','Я покупаю билет']),
ex('text','Переведите: «Я посетил Лондон вчера».',['I visited London yesterday','Yesterday I visited London'],'Visited — правильная форма Past Simple для visit.'),
ex('order','Составьте вопрос.','Did you enjoy the trip','Did + подлежащее + начальная форма.',['trip','enjoy','the','Did','you']) ]},
{'id':'future-plans','title':'Планы на путешествие','level':'A2','chapter':'03 · Новые истории','description':'Расскажите о намерениях и договоритесь о поездке.','minutes':6,'xp':70,'free':False,'grammar':'Be going to + глагол — намерение. I am going to travel. Are you going to travel?','vocabulary':[{'word':'travel','ru':'путешествовать','uz':'sayohat qilmoq'},{'word':'tomorrow','ru':'завтра','uz':'ertaga'},{'word':'ticket','ru':'билет','uz':'chipta'}],'examples':['I am going to travel tomorrow.','She is going to book a room.','Are you going to buy a ticket?'],'exercises':[
ex('gap','She ___ going to book a room.','is','She is going to + начальная форма.',['am','are','is']),
ex('order','Составьте намерение.','I am going to travel','I + am + going to + travel.',['to','travel','am','I','going']),
ex('correction','Исправьте: I going to buy a ticket.', ['I am going to buy a ticket',"I'm going to buy a ticket"],'Перед going to необходима форма be — здесь am.'),
ex('text','Переведите: «Мы собираемся путешествовать».',['We are going to travel',"We're going to travel"],'We are going to travel — намерение путешествовать.'),
ex('choice','Are you going to travel tomorrow? Выберите краткий положительный ответ.','Yes, I am.','В кратком ответе сохраняется am.',['Yes, I do.','Yes, I am.','Yes, I going.']) ]}
]
for lesson in lessons:
    (root/(lesson['id']+'.json')).write_text(json.dumps(lesson,ensure_ascii=False,indent=2)+'\n')
