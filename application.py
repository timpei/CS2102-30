import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, g, jsonify

# this is the path of the sqlite3 db file
DATABASE = 'tmp/flashcard.db'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# this is an attribute that will be used by flask
# setting DEBUG to true will allow you to trace server activities from terminal
DEBUG = True
app = Flask(__name__)
app.config.from_object(__name__)

def make_dicts(cursor, row):
    return dict((cursor.description[idx][0], value)
                for idx, value in enumerate(row))

# used to run SQL queries
# setting one to true will only return the first (or only) result
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

# gets an instance of the database cursor 
# (which allows you to run sqlite actions)
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_to_database()
    db.row_factory = make_dicts
    return db

# opens a sqlite3 connection
def connect_to_database():
    return sqlite3.connect(DATABASE)

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# this is run to initialize the database
# used if the server is started for the first time
def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()


"""
WEB PAGES
"""

@app.route('/')
def login():
    banner = request.args.get('banner')
    type = 'danger'
    if banner == 'signup_success':
        bannerMessage = 'Sign up was successful! Please login below.'
        type = 'success'
    elif banner == 'signup_failure':
        bannerMessage = 'Sign up was unsuccessful. Please try again'
    elif banner == 'login_failure':
        bannerMessage = 'Your username or password is incorrect.'
    else:
        bannerMessage = None


    # get aggregates
    usercount = query_db("SELECT COUNT(*) AS count FROM User", one=True)
    setcount = query_db("SELECT COUNT(*) AS count FROM CardSet", one=True)
    cardcount = query_db("SELECT COUNT(*) AS count FROM Flashcard", one=True)
    langcount = query_db("SELECT COUNT(*) AS count FROM Language", one=True)
    catcount = query_db("SELECT COUNT(*) AS count FROM Category", one=True)

    return render_template('login.html', message=bannerMessage, type=type,
                           usercount=usercount, setcount=setcount, cardcount=cardcount,
                           langcount=langcount, catcount=catcount)

@app.route('/submit_login', methods=['POST'])
def submitLogin():
    # get the post variable for username (from the form)
    username=request.form['username']
    password=request.form['password']

    # get user information
    user = query_db('SELECT * FROM User WHERE username = ?',
                    [username], one=True)

    # if user doesn't exist or password is incorrect
    # TODO(sumin): Decode password
    if user is None or user["password"] != password:
        return redirect(url_for('login', banner='login_failure'))

    return redirect(url_for('userDashboard', username=username))

@app.route('/submit_signup', methods=['POST'])
def submitSignup():
    data = request.get_json()
    cursor = get_db().cursor()
    cursor.execute("""INSERT INTO User
                      (username, firstName, lastName, email, birthday, password,
                      isAdmin, avatar, lastLogin, registerDate) VALUES
                      (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      [data['username'], data['firstName'], data['lastName'], data['email'], data['birthday'],
                       data['password'], False, data['avatar'], datetime.now(), datetime.now()])
    get_db().commit()
    return 'True'

@app.route('/user/<username>')
def userDashboard(username):
    banner = request.args.get('banner')
    type = 'success'
    if banner == 'create_success':
        bannerMessage = 'Success! Your set has been created.'
    elif banner == 'edit_success':
        bannerMessage = 'Success! The set has be updated.'
    elif banner == 'profile_edit_success':
        bannerMessage = 'Success! Your profile has be updated.'
    elif banner == 'not_admin':
        bannerMessage = 'Sorry, you do not have edit privileges.'
        type = 'danger'
    else:
        bannerMessage = None

    languages = query_db('SELECT * FROM Language')
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    myCardSets = [cardSet for cardSet in query_db("""SELECT * FROM CardSet c, UserCollection u
                                                     WHERE u.username = ?
                                                     AND c.setID = u.setID""",
                                                  [username])]
    allCardSets = [cardSet for cardSet in query_db('SELECT * FROM CardSet WHERE creator <> ? LIMIT 5', [username])]

    # update user last login time
    cursor = get_db().cursor()
    cursor.execute("""UPDATE User SET lastLogin = CURRENT_TIMESTAMP WHERE username = ?""", [username])
    get_db().commit()

    return render_template('user.html', languages=languages, user=user, myCardSets=myCardSets,
                           allCardSets=allCardSets, message=bannerMessage, type=type,
                           avatar=getAvatarColor(user))

@app.route('/signup')
@app.route('/user/<username>/profile')
def profile(username=None):
    mode = 'edit' if username else 'signup'
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    return render_template('profile.html', user=user, mode=mode, avatar=getAvatarColor(user))

# TODO(tim): Change add card button ui (put it on top of the delete button)
@app.route('/user/<username>/create')
@app.route('/user/<username>/edit/<setID>')
def createSet(username, setID=None):
    user = query_db('SELECT * FROM User WHERE username = ?', 
                    [username], one=True)
    languages = query_db('SELECT name FROM Language ORDER BY langID')
    categories = query_db('SELECT name FROM Category ORDER BY catID')
    mode = 'edit' if setID else 'create'

    if mode == 'edit' and user['isAdmin'] == 0:
        return redirect(url_for('userDashboard', username=username, banner='not_admin'))

    return render_template('create.html', user=user, 
                                        languages=languages,
                                        categories=categories,
                                        mode=mode,
                                        avatar=getAvatarColor(user))

@app.route('/create_set/<username>', methods=['POST'])
def submitSetCreate(username):
    data = request.get_json()
    cursor = get_db().cursor()
    if 'description' in data:
        cursor.execute('INSERT INTO CardSet '
                         '(title, description, language, creator, lastUpdate, category, viewCount) VALUES '
                         '(?, ?, ?, ?, ?, ?, 0)',
                          [data['title'], data['description'], data['language'], data['creator'],
                          datetime.now(), data['category']])
    else:
        cursor.execute('INSERT INTO CardSet '
                         '(title, language, creator, lastUpdate, category, viewCount) VALUES '
                         '(?, ?, ?, ?, ?, 0)',
                          [data['title'], data['language'], data['creator'],
                          datetime.now(), data['category']])
    setId = cursor.lastrowid

    cursor.execute('INSERT INTO UserCollection  VALUES (?, ?)',
                    [data['creator'], setId])

    for card in data['flashcards']:
        cursor.execute('INSERT INTO Flashcard'
                        '(word, translation, setID) VALUES'
                        '(?, ?, ?)',
                        [card['word'], card['translation'], setId])
    get_db().commit()
    return 'True'

@app.route('/edit_set/<setID>', methods=['POST'])
def submitSetEdit(setID):
    data = request.get_json()
    cursor = get_db().cursor()

    if 'description' in data:
        cursor.execute("""UPDATE CardSet
                          SET title = ?, description = ?, language = ?, lastUpdate = ?, category = ?
                          WHERE setID = ?""",
                          [data['title'], data['description'], data['language'],
                          datetime.now(), data['category'], setID])
    else:
        cursor.execute("""UPDATE CardSet
                          SET title = ?, language = ?, lastUpdate = ?, category = ?
                          WHERE setID = ?""",
                          [data['title'], data['language'], datetime.now(), data['category'], setID])

    # first delete all the flashcards in the set
    cursor.execute("DELETE FROM Flashcard WHERE setID = ?", [setID])

    # add all the new flashcards
    for card in data['flashcards']:
        cursor.execute('INSERT INTO Flashcard'
                        '(word, translation, setID) VALUES'
                        '(?, ?, ?)',
                        [card['word'], card['translation'], setID])
    get_db().commit()
    return 'True'

@app.route('/user/<username>/delete/<setID>', methods=['GET'])
def submitSetDelete(username, setID):
    cursor = get_db().cursor()

    cursor.execute("DELETE FROM Flashcard WHERE setID = ?", [setID])
    cursor.execute("DELETE FROM CardSet WHERE setID = ?", [setID])
    cursor.execute("DELETE FROM UserCollection WHERE setID = ?", [setID])

    get_db().commit()
    return redirect(url_for('userDashboard', username=username))

@app.route('/user/<username>/search')
def searchSet(username):
    user = query_db('SELECT * FROM User WHERE username = ?', 
                    [username], one=True)
    languages = query_db('SELECT name FROM Language ORDER BY langID')
    categories = query_db('SELECT name FROM Category ORDER BY catID')

    return render_template('search.html', user=user, 
                                        languages=languages,
                                        categories=categories,
                                        avatar=getAvatarColor(user))


@app.route('/advancedSearch/<username>', methods=['POST'])
def advancedSearch(username):
    data = request.get_json()
    
    query = "SELECT s.setID, s.title, s.description, l.name AS language, \
                    c.name AS category, s.creator, s.lastUpdate, s.viewCount \
            FROM CardSet s, Language l, Category c \
            WHERE s.title LIKE '%' || ? || '%' \
            AND s.description LIKE '%' || ? || '%' \
            AND s.creator LIKE '%' || ? || '%' \
            AND l.langID = s.language \
            AND c.catID = s.category"
    queryData = [data['title'], data['description'], data['creator']]


    if int(data['language']) != 0:
        query += " AND l.langID = ?"
        queryData.append(int(data['language']))

    if int(data['category']) != 0:
        query += " AND c.catID = ?"
        queryData.append(int(data['category']))

    results = query_db(query, queryData)

    return jsonify(results=results)


@app.route('/quickSearch/<username>', methods=['POST'])
def quickSearch(username):
    data = request.get_json()
    results = query_db("SELECT s.setID, s.title, s.description, l.name AS language, \
                                c.name AS category, s.creator, s.lastUpdate, s.viewCount \
                        FROM CardSet s, Language l, Category c \
                        WHERE title LIKE '%' || ? || '%' \
                        AND l.langID = s.language \
                        AND c.catID = s.category", 
                        [data['query']])

    return jsonify(results=results)


@app.route('/getUser/<username>', methods=['GET'])
def getUser(username):
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    return jsonify(user=user)


@app.route('/editProfile/<username>', methods=['POST'])
def submitEditProfile(username):
    data = request.get_json()
    cursor = get_db().cursor()
    cursor.execute("""UPDATE User
                      SET password = ?, firstName = ?, lastName = ?, email = ?, birthday = ?, avatar = ?
                      WHERE username = ?""",
                      [data['password'], data['firstName'], data['lastName'], data['email'],
                       data['birthday'], data['avatar'], username])
    get_db().commit()
    return 'True'


@app.route('/flashcards/<setID>', methods=['GET'])
def getFlashcards(setID):
    flashcards = query_db('SELECT * FROM Flashcard WHERE setID = ?', [setID])
    print flashcards
    return jsonify(flashcards=flashcards)

@app.route('/set/<setID>', methods=['GET'])
def getSet(setID):
    cardSet = query_db("SELECT * FROM CardSet WHERE setID = ?", 
                        [setID], one=True)
    return jsonify(result=cardSet) 

@app.route('/user/<username>/addSet/<setID>', methods=['POST'])
def addUserCollection(username, setID):
    cursor = get_db().cursor()
    cursor.execute('INSERT INTO UserCollection VALUES (?, ?)', [username, setID])
    get_db().commit()
    # TODO(sumin): catch error
    return 'True'

@app.route('/user/<username>/removeSet/<setID>', methods=['POST'])
def removeUserCollection(username, setID):
    cursor = get_db().cursor()
    cursor.execute('DELETE FROM UserCollection WHERE username = ? AND setID = ?', [username, setID])
    get_db().commit()
    # TODO(sumin): catch error
    return 'True'

@app.route('/user/<username>/hasSet/<setID>', methods=['GET'])
def getHasSet(username, setID):
    hasSet = query_db("SELECT 1 FROM UserCollection WHERE username = ? AND setID = ?",
                      [username, setID], one=True)
    hasSet = hasSet is not None
    return jsonify(hasSet=hasSet)

@app.route('/user/<username>/view/<setID>')
def viewSet(username, setID):
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    cardSet = query_db("SELECT s.setID, s.title, s.description, l.name AS language, \
                               c.name AS category, s.creator, s.lastUpdate, s.viewCount \
                        FROM CardSet s, Language l, Category c \
                        WHERE setID = ? \
                        AND l.langID = s.language \
                        AND c.catID = s.category", [setID], one=True)
    cursor = get_db().cursor()
    cursor.execute("""UPDATE CardSet SET viewCount = ? WHERE setID = ?""",
                          [cardSet['viewCount']+1, setID])
    get_db().commit()
    return render_template('browse.html', user=user, cardSet=cardSet, avatar=getAvatarColor(user))


@app.route('/user/<username>/explore')
def exploreSets(username):
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    languages = query_db("""SELECT l.name, ls.langCount 
                            FROM Language l
                            LEFT JOIN  LanguageSetCount ls
                            ON l.langID = ls.langID
                            ORDER BY l.langID""")
    categories = query_db("""SELECT c.name, cs.catCount 
                            FROM Category c
                            LEFT JOIN CategorySetCount cs
                            ON c.catID = cs.catID
                            ORDER BY c.catID""")
    allCardSets = [cardSet for cardSet in query_db('SELECT * FROM CardSet')]
    print categories
    return render_template('explore.html', user=user, 
                                        languages=languages,
                                        categories=categories,
                                        title="Browsing all sets",
                                        sets=allCardSets,
                                        avatar=getAvatarColor(user))

@app.route('/user/<username>/explore/<group>/<index>')
def exploreGroups(username, group, index):
    user = query_db('SELECT * FROM User WHERE username = ?', [username], one=True)
    languages = query_db("""SELECT l.name, ls.langCount 
                            FROM Language l
                            LEFT JOIN  LanguageSetCount ls
                            ON l.langID = ls.langID
                            ORDER BY l.langID""")
    categories = query_db("""SELECT c.name, cs.catCount 
                            FROM Category c
                            LEFT JOIN CategorySetCount cs
                            ON c.catID = cs.catID
                            ORDER BY c.catID""")

    if group == 'category':
        allCardSets = query_db('SELECT * FROM CardSet WHERE category == ?', [int(index)])
        name = categories[int(index)-1]['name']
    elif group == 'featured':
        if index == 'popular':
            allCardSets = query_db("""SELECT c.setID, c.title, c.description, m.numCollections
                                    FROM MostCollected m, CardSet c 
                                    WHERE m.setID = c.setID
                                    ORDER BY m.numCollections""")
            name = 'most collected sets'
        if index == 'biggest':
            allCardSets = query_db("""SELECT c.setID, c.title, c.description, b.numCards
                                    FROM BiggestSet b, CardSet c 
                                    WHERE b.setID = c.setID
                                    ORDER BY b.numCards""")
            name = 'biggest sets'
    else:
        allCardSets = [cardSet for cardSet in query_db('SELECT * FROM CardSet WHERE language == ?', [int(index)])]
        name = languages[int(index)-1]['name']

    return render_template('explore.html', user=user, 
                                        languages=languages,
                                        categories=categories,
                                        title='Browsing "%s"' % name,
                                        sets=allCardSets,
                                        group=group,
                                        avatar=getAvatarColor(user))

def getAvatarColor(user):
    if user is None:
        return -1
    color = ["#F25E5E", "#F2BE6B", "#F2EE6B", "#6BF29F", "#6BB3F2", "#BBA3F4"]
    return color[user['avatar']-1]

# starts the server 
if __name__ == '__main__':

    # first check to see of the machine has set an environment variable for port
    # if not, use port 5000
    port = int(os.environ.get('PORT', 5000))

    # if the database does not exist, initialize it
    if not os.path.exists('tmp'):  
        os.makedirs('tmp')
        init_db()

    # starts the server at localhost
    app.run(host='0.0.0.0', port=port)
