pip install -r requirements.txt
flask shell <<< "from app import db; db.create_all()"