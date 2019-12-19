#Import Flask Library
from flask import Flask, render_template, request, session, url_for, redirect, send_file
import os
import uuid
import hashlib
import pymysql.cursors
from functools import wraps
import time
from datetime import datetime

#Initialize the app from Flask
app = Flask(__name__)
app.secret_key = 'super secret key'
IMAGES_DIR = os.path.join(os.getcwd(), "photos")

#Configure MySQL
conn = pymysql.connect(host='localhost',
                       port = 3306,
                       user='root',
                       password='',
                       db='finstagram',
                       charset='utf8mb4',
                       cursorclass=pymysql.cursors.DictCursor,
                       autocommit=True
                    )
#if a user is not logged in they wont be able to access route
def loggedIn(i):
    @wraps(i)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return i(*args, **kwargs)
    return dec

#Define a route to initial function
@app.route('/')
def index():
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")

#Define route for login
@app.route('/login', methods=["GET"])
def login():
    return render_template("login.html")

#Define route for register
@app.route('/register', methods=["GET"])
def register():
    return render_template("register.html")

#Define route for Home
@app.route('/home')
@loggedIn
def home():
    return render_template("home.html", username=session["username"])

#Define route for posting image
@app.route('/upload', methods=["GET"])
@loggedIn
def upload():
    return render_template("upload.html")
    
#Define route for photos
@app.route('/images',methods=["GET"])
@loggedIn
def images():
    photoInfo={}
    query = "SELECT photo.photoID, photo.postingdate, photo.photoPoster, photo.filepath, photo.caption FROM photo, belongto, sharedwith where belongto.owner_username = %s AND belongto.groupName = sharedwith.groupName AND belongto.owner_username = sharedwith.groupOwner AND photo.photoID = sharedwith.photoID UNION (SELECT photo.photoID, photo.postingdate, photo.photoPoster, photo.filepath, photo.caption FROM photo, follow WHERE (photo.photoPoster = %s) OR follow.username_follower = %s AND follow.followstatus = 1 AND photo.allFollowers = 1) ORDER BY postingdate DESC"
    with conn.cursor() as cursor:
        cursor.execute(query,(session["username"],session["username"],session["username"]))    
    data = cursor.fetchall()	
    for p in data:
        query = "SELECT firstName, lastName FROM tagged NATURAL JOIN person WHERE photoID = %s AND tagstatus = 1"
        with conn.cursor() as initialCursor:
            initialCursor.execute(query, (p["photoID"]))
        pInfo = initialCursor.fetchall()
        initialCursor.close()
        photoInfo[p["photoID"]] = pInfo
    query = "SELECT photoID FROM tagged WHERE username = %s AND tagstatus=0"
    with conn.cursor() as cursor:
        cursor.execute(query, (session["username"]))
    pInfo2 = cursor.fetchall()
    cursor.close()
    return render_template("images.html", images=data, pendingTags=pInfo2, extra=photoInfo)

@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    imageLoc = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(imageLoc):
        return send_file(imageLoc, mimetype="image/jpg")

#accessing and returning the ID of a photo
def getPhotoID(postingdate):
	query = "SELECT photoID, postingdate FROM photo WHERE postingdate = %s and photoPoster = %s"
	with conn.cursor() as cursor:
		cursor.execute(query, (postingdate, session["username"]))
	data = cursor.fetchone()
	cursor.close()
	return data["photoID"]

#displaying the photo info
def photoIsVisible(pID,username):
    #determine if the photo is visible to the user
	query = "SELECT photoID FROM (SELECT photo.photoID, photo.photoPoster, photo.postingdate, photo.filepath, photo.caption FROM photo, belongto, sharedwith where belongto.owner_username=%s AND belongto.groupName=share.groupName AND belongto.owner_username=sharedwith.groupOwner AND photo.photoID=sharedwith.photoID UNION (SELECT photo.photoID, photo.postingdate, photo.photoPoster, photo.filepath, photo.caption FROM photo, follow WHERE (photo.photoPoster = %s) OR follow.username_follower = %s AND follow.followstatus = 1))"
	with conn.cursor() as cursor:
		cursor.execute(query, (username, username, username))
	data = cursor.fetchall()
	cursor.close()
	print("Photo Info: " + str(data))
	for infoIndex in data:
		print("current photo " + str(infoIndex["photoID"]) + "=: " + str((pID)) + str(infoIndex["photoID"]))
		if str(infoIndex["photoID"]) == pID:
			return 1
	return 0

#identify the group owner
def getGroupOwner(group_name):
    query = "SELECT groupOwner FROM friendgroup WHERE groupName = %s"
    with conn.cursor() as cursor:
        cursor.execute(query, (group_name))
    data = cursor.fetchone()
    cursor.close()
    return data

#sharing a photo with a designated group
def sharePhoto(group_name):
    firstQuery = "SELECT * FROM belongto WHERE groupName = %s AND (owner_username = %s OR member_username = %s)"
    secondQuery = "SELECT * from friendgroup where groupOwner = %s AND groupName = %s"
    with conn.cursor() as cursor1:
        cursor1.execute(firstQuery, (group_name, session["username"], session["username"]))
    with conn.cursor() as cursor2:
        cursor2.execute(secondQuery, (session["username"], group_name))
    dataVal1 = cursor1.fetchall()
    dataVal2 = cursor2.fetchall()
    cursor1.close()
    cursor2.close()
    for i in dataVal1:
        if (i["groupOwner"] == session["username"]) or (i["username"] == session["username"]):
            return 1
    for i in dataVal2:
        if (i["groupOwner"] == session["username"]) or (i["username"] == session["username"]):
            return 1
    return 0

#Define route to upload an image
@app.route("/uploadImage", methods=["GET","POST"])
@loggedIn
def upload_image():
    if request.files:
        requestData = request.form
        image_file = request.files.get("imageToUpload","")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        
        postingdate = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        if requestData["caption"]:
            caption = requestData["caption"]
        
        if requestData["groupName"]:
            groupName = requestData["groupName"]
            group_dict = getGroupOwner(groupName)
            if not sharePhoto(groupName):
                if (requestData["private"].lower()) == "private":
                    return render_template("upload.html", message="Group does not exist or you do not have access.")

        if (requestData["private"].lower()) == "private":
            query = "INSERT INTO photo (postingdate, filepath, photoPoster, allFollowers) VALUES (%s, %s, %s,0)"
            with conn.cursor() as cursor:
                cursor.execute(query, (postingdate, image_name, session["username"]))
            cursor.close()
            photoID = getPhotoID(postingdate)
            query1 = "UPDATE photo SET allFollowers=0 WHERE photoID=%s"
            query2 = "INSERT INTO sharedwith (groupName,groupOwner,photoID) VALUES (%s,%s,%s)"
            group_owner = group_dict["groupOwner"]
            
            with conn.cursor() as firstCursor:
                firstCursor.execute(query1, (photoID))
            with conn.cursor() as secondCursor:
                secondCursor.execute(query2, (groupName, group_owner, photoID))
            firstCursor.close()
            secondCursor.close()
        else:
            query = "INSERT INTO photo (postingdate, filepath, photoPoster, allFollowers) VALUES (%s, %s, %s, 1)"
            with conn.cursor() as cursor:
                cursor.execute(query, (postingdate, image_name, session["username"]))
            photoID = getPhotoID(postingdate)
        if caption:
            photoID = getPhotoID(postingdate)
            query = "UPDATE photo SET caption=%s WHERE photoID=%s AND photoPoster = %s"
            with conn.cursor() as cursor:
                cursor.execute(query, (caption, photoID, session["username"]))
        message = "Image has been successfully uploaded."
        return render_template("upload.html", message=message)
    else:
            message = "Failed to upload image."
            return render_template("upload.html", message=message)
    return render_template("upload.html") 

#Define route for following
@app.route("/follow", methods=["GET"])
def follow():
	query = "SELECT * FROM follow WHERE username_follower = %s AND followstatus = 0"
	with conn.cursor() as cursor:
		cursor.execute(query, (session["username"]))
	data = cursor.fetchall()
	cursor.close()
	return render_template("follow.html", data=data)

@app.route("/accept", methods=["POST"])
def acceptRequest():
    if request.form:
        cursor = conn.cursor()
        requestData = request.form
        currentUser = session["username"]
        if requestData['username_follower']:
            follower = requestData['username_follower']
        if requestData['accept']:
            acceptVal = requestData['accept']
            if acceptVal == "Accept":
                query = "UPDATE follow SET followstatus=1 WHERE username_follower=%s AND username_followed=%s"
                message = "Follow Accepted"
            elif acceptVal == "Decline":
                query = "DELETE FROM follow WHERE userame_follower=%s AND username_followed=%s"
            cursor.execute(query, (currentUser, follower))
            cursor.close()
        return render_template("follow.html", message=message)

@app.route("/showFollowRequests", methods=["POST"])
@loggedIn
def showFollowRequests():
    if request.form["button2"]=="Accept":
        pass
    if request.form["button2"]=="Decline":
        query = "DELETE FROM follow WHERE username_followed=%s AND username_follower=%s" 
        with conn.cursor() as cursor: 
            cursor.execute(query,(session["username"]))
        message= "User has been declined."
    return render_template("follow.html",message=message)
    
@app.route("/privateImage", methods=["POST"])
@loggedIn
def privateImage():
    if request.form:
        requestData = request.form
        if requestData["private"]:
            firstQuery = "UPDATE photo SET allFollowers = 0 WHERE photoID = %s" 
            secondQuery = "INSERT INTO sharedwith (groupName, groupOwner, photoID) VALUES (%s,%s,%s)"
            groupName = requestData['friendgroup']
            postingdate = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            groups = getGroupOwner(groupName)
            groupOwner = groups["groupOwner"]
            pID = getPhotoID(postingdate)
            with conn.cursor() as cursor1:
                cursor1.execute(firstQuery, (p_id))
            with conn.cursor() as cursor2:
                cursor2.execute(secondQuery, (groupName, groupOwner, pID))
            cursor1.close()
            cursor2.close()

#Authenticates the login
@app.route('/loginAuth', methods=['POST'])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPassword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPassword.encode("utf-8")).hexdigest()
        with conn.cursor() as cursor:
            query = "SELECT * FROM person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, hashedPassword))
        data = cursor.fetchone()
        if data:
            session["username"] = username
            return redirect(url_for("home"))
        else:
            error = "Incorrect username or password."
        return render_template("login.html", error=error)

#Authenticates the register
@app.route('/registerAuth', methods=['POST'])
def registerAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPassword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPassword.encode("utf-8")).hexdigest()
        firstName = requestData["firstName"]
        lastName = requestData["lastName"]
        try:
            with conn.cursor() as cursor:
                query = "INSERT INTO person (username, password, firstName, lastName) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)
        return redirect(url_for("login"))
    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

@app.route("/followAuth", methods=["GET","POST"])
def followAuth():
    if request.form:
        requestData = request.form
        follower = session["username"]
        followee = requestData['username']
        username = session["username"]
        query = "SELECT * FROM follow WHERE username_followed = %s AND followstatus = 0"
        with conn.cursor() as cursor:
            cursor.execute(query, (username))
        cursor.close()
        try:
            with conn.cursor() as cursor:
                query = "INSERT INTO follow (username_followed, username_follower, followstatus) VALUES (%s, %s, 0)"
                cursor.execute(query, (follower, followee))
            error = "A follow request has been sent to the user."
        except pymysql.err.IntegrityError:
            error = "%s does not exist or follow request already sent." % (followee)
            return render_template('follow.html', error=error)
        return render_template('follow.html', error=error)
    error = "An error has occurred. Please try again."
    return render_template("follow.html", error=error)

@app.route('/logout', methods=["GET"])
def logout():
    session.pop('username')
    return redirect('/')
'''
if __name__ == "__main__":
	if not os.path.isdir("images"):
		os.mkdir(IMAGES_DIR)
	app.run()
'''

#if __name__ == "__main__":
    #app.run('127.0.0.1', 5000, debug = True)

app.run(debug=True)
