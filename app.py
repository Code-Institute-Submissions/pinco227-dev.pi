from bson.objectid import ObjectId
from datetime import date
from flask import (
    Flask, flash, render_template,
    redirect, request, session, url_for, Markup, send_from_directory, jsonify, make_response)
from flask_breadcrumbs import Breadcrumbs, register_breadcrumb
from flask_mail import Mail, Message
from flask_pymongo import PyMongo
from forms import *
from functools import wraps
from html5lib_truncation import truncate_html
import pydf
import pymongo
import random
import re
import os
import secure

if os.path.exists("env.py"):
    import env

# Initialize app
app = Flask(__name__)

# Config app
app.config["MONGO_DBNAME"] = os.environ.get("MONGO_DBNAME")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["RECAPTCHA_PUBLIC_KEY"] = os.environ.get("RC_SITE_KEY")
app.config["RECAPTCHA_PRIVATE_KEY"] = os.environ.get("RC_SECRET_KEY")
app.config['UPLOAD_PATH'] = 'uploads'
app.config['UPLOAD_EXTENSIONS'] = ['.png', '.jpg', '.jpeg', '.gif']
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
mail_settings = {
    "MAIL_SERVER": 'smtp.gmail.com',
    "MAIL_PORT": 465,
    "MAIL_USE_TLS": False,
    "MAIL_USE_SSL": True,
    "MAIL_USERNAME": os.environ.get("EMAIL_USER"),
    "MAIL_PASSWORD": os.environ.get("EMAIL_PASSWORD")
}
app.config.update(mail_settings)

if not os.path.exists(app.config['UPLOAD_PATH']):
    os.makedirs(app.config['UPLOAD_PATH'])

# Initializations / Global vars
Breadcrumbs(app=app)
mongo = PyMongo(app)
mail = Mail(app)
secure_headers = secure.Secure()
settings = mongo.db.settings.find_one(
    {"_id": ObjectId(os.environ.get("DB_SETTINGS_ID"))})


@app.after_request
def set_secure_headers(response):
    """Set Secure HTTP Headers

    Args:
        response (obj): response object to modify

    Returns:
        obj: modified response
    """
    secure_headers.framework.flask(response)
    return response


@app.context_processor
def context_processor():
    """Inject settings and links variables to all templates

    Returns:
        dict: settings and links db collections
    """
    links = list(mongo.db.links.find())
    return dict(settings=settings, links=links)


@app.errorhandler(413)
def too_large(e):
    """Error handler for error 413 TOO LARGE

    Args:
        e (obj): error obj

    Returns:
        obj: json response
    """
    return make_response(jsonify({"message": "File is too large!"}), 413)


@app.errorhandler(404)
def page_not_found(e):
    """Error handler for error 404 NOT FOUND

    Args:
        e (obj): error obj

    Returns:
        function: redirect to home or dashboard
    """
    flash("Page not found!", "danger")
    if request.path.split('/')[1] == "admin":
        return redirect(url_for('admin'))

    return redirect(url_for('home'))


@app.route('/browserconfig.xml')
def sendfile():
    """Sends browserconfig.xml from static folder when accessed from root

    Returns:
        funct: returns file
    """
    return send_from_directory('static', 'browserconfig.xml')


@app.route('/uploads/', defaults={'filename': False})
@app.route('/uploads/<filename>')
def uploads(filename):
    """Route to access uploaded files and to have url_for uploads as flask variable

    Args:
        filename (string): requested file name

    Returns:
        function: returns requested file if exists or no-photo.jpg if it doesn't
    """
    if filename and os.path.exists(os.path.join(app.config['UPLOAD_PATH'], filename)):
        return send_from_directory(app.config['UPLOAD_PATH'],
                                   filename)
    else:
        return send_from_directory('static/images', 'no-photo.jpg')


@app.route('/cv')
def get_cv():
    """Route that generates pdf file from html jinja template

    Returns:
        obj: response with pdf headers and content
    """
    root = request.url_root
    jobs = list(mongo.db.experience.find().sort("order", 1))
    schools = list(mongo.db.education.find().sort("order", 1))
    skills = list(mongo.db.skills.find().sort("percentage", -1))
    projects = list(mongo.db.projects.find())
    testimonials = list(mongo.db.testimonials.find(
        {"approved": True}).limit(5))
    html = render_template("cv.html", jobs=jobs,
                           schools=schools, skills=skills, projects=projects, testimonials=testimonials, root=root)
    filename = settings['name'].replace(' ', '-').lower()
    pdf = pydf.generate_pdf(html, page_size="A4", margin_bottom="0.75in",
                            margin_top="0.75in", margin_left="0.5in", margin_right="0.5in", image_dpi="300")
    # pdf = pdfkit.from_string(html, False, options=options)
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=" + \
        filename+".pdf"
    return response


@app.route("/home")
@app.route('/')
@register_breadcrumb(app, '.', 'Home')
def home():
    """Landing page route

    Returns:
        function: renders landing page from html jinja template
    """
    skills = list(mongo.db.skills.find())
    education = list(mongo.db.education.find().sort("order", 1))
    experience = list(mongo.db.experience.find().sort("order", 1))
    testimonials = list(mongo.db.testimonials.find({"approved": True}))
    return render_template("landing.html", skills=skills, education=education, experience=experience, testimonials=testimonials)


@app.route('/write-testimonial', methods=["GET", "POST"])
@register_breadcrumb(app, '.write-testimonial', 'Write Testimonial')
def add_testimonial():
    """Write testimonial page route

    Returns:
        function: renders page from html jinja template
    """
    form = WriteTestimonialForm()
    if request.method == "POST":
        if form.validate_on_submit():
            testimonial = {
                "author": form.name.data,
                "role": form.role.data,
                "text": form.text.data,
                "approved": False
            }
            mongo.db.testimonials.insert_one(testimonial)
            flash("Thank you for your feedback!", "success")
            return redirect(url_for("home"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("write-testimonial.html", form=form)


@app.route('/portfolio')
@register_breadcrumb(app, '.portfolio', 'Portfolio')
def portfolio():
    """Portfolio page route

    Returns:
        function: renders page from html jinja template
    """
    projects = list(mongo.db.projects.find())
    return render_template("portfolio.html", projects=projects)


def view_project_dlc(*args, **kwargs):
    """Get project details from requested url args

    Returns:
        dict: text to be displayed into breadcrumb (Project title)
    """
    slug = request.view_args['project']
    project = mongo.db.projects.find_one({"slug": slug})
    return [{'text': project['title']}]


@app.route('/portfolio/<project>')
@register_breadcrumb(app, '.portfolio.project', '', dynamic_list_constructor=view_project_dlc)
def get_project(project):
    """Project page route

    Args:
        project (string): requested project slug

    Returns:
        function: renders page from html jinja template
    """
    project = mongo.db.projects.find_one({"slug": project})
    return render_template("project.html", project=project)


@app.route('/blog')
@register_breadcrumb(app, '.blog', 'Blog')
def blog():
    """Blogs page route

    Returns:
        function: renders page from html jinja template
    """
    blogs = list(mongo.db.blogs.find())
    for i, blog in enumerate(blogs):
        blog["body"] = truncate_html(
            blog["body"], 200, end=' ...', break_words=True)
        blogs[i] = blog
    return render_template("blog.html", blogs=blogs)


def view_blog_dlc(*args, **kwargs):
    """Get blog post details from requested url args

    Returns:
        dict: text to be displayed into breadcrumb (Blog title)
    """
    slug = request.view_args['post']
    post = mongo.db.blogs.find_one({"slug": slug})
    return [{'text': post['title']}]


@app.route('/blog/<post>')
@register_breadcrumb(app, '.blog.post', '', dynamic_list_constructor=view_blog_dlc)
def get_post(post):
    """Blog post page route

    Args:
        post (string): requested post slug

    Returns:
        function: renders page from html jinja template
    """
    post = mongo.db.blogs.find_one({"slug": post})
    return render_template("blog-post.html", post=post)


@app.route('/contact', methods=['GET', 'POST'])
@register_breadcrumb(app, '.contact', 'Contact')
def contact():
    """Conact page route

    Returns:
        function: renders page from html jinja template
    """
    form = ContactForm()
    if request.method == "POST":
        if form.validate_on_submit():
            msg = Message(subject="[Dev.PI] " + form.subject.data,
                          sender=app.config.get("MAIL_USERNAME"),
                          recipients=[app.config.get("MAIL_USERNAME")],
                          body=form.name.data + "(" + form.email.data + "): " + form.message.data)
            mail.send(msg)
            flash(
                "Thank you for your message! I will get back to you shortly.", "success")
            return redirect(url_for("contact"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("contact.html", form=form)


# ADMIN PANEL
def login_required(flash_message=False):
    """Function decorator to check for login

    Args:
        flash_message (bool, optional): Message to be sent via Flash. If left empty then no message is sent. Defaults to False.
    """
    def inner_function(f):
        """Wrapper function in order to get argument into decorator

        Args:
            f (function): Decorated function

        Returns:
            function: Function after being decorated
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user"):
                flash(flash_message, "danger") if flash_message else None
                return redirect(url_for("login"))
            else:
                return f(*args, **kwargs)
        return decorated_function
    return inner_function


@app.route('/admin')
@login_required()
def admin():
    """ADMIN Dashboard page route

    Returns:
        function: renders page from html jinja template
    """
    testimonials = mongo.db.testimonials.count_documents({})
    blogs = mongo.db.blogs.count_documents({})
    projects = mongo.db.projects.count_documents({})
    skills = mongo.db.skills.count_documents({})
    education = mongo.db.education.count_documents({})
    experience = mongo.db.experience.count_documents({})
    unapproved_testimonials = mongo.db.testimonials.count_documents({
                                                                    "approved": False})
    return render_template("admin/dashboard.html", blogs=blogs, projects=projects, skills=skills, education=education, experience=experience, testimonials=testimonials, unapproved_testimonials=unapproved_testimonials)


@app.route('/admin/files', methods=['PATCH', 'DELETE'])
@login_required()
def files():
    """Route for file manipulation (upload, delete) that works with API calls

    Returns:
        obj: json response
    """
    if "collection" in request.args:
        coll = request.args.get('collection')

        # DELETE request
        if request.method == "DELETE":
            # Check if document id was sent as argument
            if "docid" in request.args or coll == "settings":
                if coll == "settings":
                    doc_id = settings["_id"]
                    coll_dict = settings
                else:
                    doc_id = request.args.get('docid')
                    coll_dict = mongo.db[coll].find_one(
                        {"_id": ObjectId(doc_id)})
                photos = list(filter(None, coll_dict["photos"].split(',')))

                # Check if photo key (position starting with 0) was sent as argument and set to 0 if not
                photo_key = request.args.get(
                    'photokey') if 'photokey' in request.args else 0
                photo = photos[int(photo_key)].strip()

                # Remove file from the list
                del photos[int(photo_key)]
                new_db_photos = ','.join(photos)
                updated_coll = {
                    "photos": new_db_photos
                }
                # Update database with new files list
                mongo.db[coll].update({"_id": ObjectId(doc_id)}, {
                    "$set": updated_coll})

                # Check if selected photo exists and delete from server
                if photo and os.path.exists(os.path.join(app.config['UPLOAD_PATH'], photo)):
                    os.remove(os.path.join(app.config['UPLOAD_PATH'], photo))
                    return make_response(jsonify({"message": f"File {photo} successfully deleted!"}), 200)
                else:
                    return make_response(jsonify({"message": "Something went wrong!"}), 400)
            else:
                # Check if file src was sent as argument and delete file from server
                if ("src" in request.args) and request.args.get('src') and os.path.exists(os.path.join(app.config['UPLOAD_PATH'], request.args.get('src'))):
                    os.remove(os.path.join(
                        app.config['UPLOAD_PATH'], request.args.get('src')))
                    return make_response(jsonify({"message": f"File {request.args.get('src')} successfully deleted!"}), 200)
                else:
                    return make_response(jsonify({"message": "Something went wrong!"}), 400)
        # PATCH request
        elif request.method == "PATCH":
            uploaded_file = request.files["files"]
            response = {}
            filename = ''
            if uploaded_file.filename != '':
                # Check if document id was sent as argument and set filename as truncated slug + random number
                if "docid" in request.args or coll == "settings":
                    if coll == "settings":
                        coll_dict = settings
                        new_filename = "settings" + \
                            str(random.randint(1111, 9999))
                    else:
                        doc_id = request.args.get('docid')
                        coll_dict = mongo.db[coll].find_one(
                            {"_id": ObjectId(doc_id)})
                        has_slug = mongo.db[coll].find(
                            {"_id": ObjectId(doc_id),
                             "slug": {"$exists": True}})
                        if has_slug:
                            new_filename = coll_dict["slug"][:25] + \
                                str(random.randint(1111, 9999))
                        else:
                            new_filename = coll + date.today().strftime("%d%m") + \
                                str(random.randint(1111, 9999))
                # Set filename as default collection name + day + month + random number
                else:
                    coll_dict = False
                    new_filename = coll + date.today().strftime("%d%m") + \
                        str(random.randint(1111, 9999))
                file_ext = os.path.splitext(uploaded_file.filename)[1]
                # Check if file extension is allowed
                if file_ext.lower() in app.config['UPLOAD_EXTENSIONS']:
                    filename = new_filename + file_ext.lower()
                    uploaded_file.save(os.path.join(
                        app.config['UPLOAD_PATH'], filename))
                    # Check if upload is made for existig db document and update it
                    if coll_dict:
                        photos = list(
                            filter(None, coll_dict["photos"].split(',')))
                        photos.append(filename)
                        updated_coll = {
                            "photos": ','.join(photos) if len(photos) > 1 else photos[0]
                        }
                        mongo.db[coll].update({"_id": ObjectId(coll_dict["_id"])}, {
                            "$set": updated_coll})
                    response = {
                        "name": uploaded_file.filename,
                        "newName": filename,
                        "message": f"File {uploaded_file.filename} was successfully uploaded",
                        "statusCode": 201
                    }
                else:
                    response = {
                        "name": uploaded_file.filename,
                        "message": "Unsupported Media Type!",
                        "statusCode": 415
                    }
                return make_response(jsonify(response), response["statusCode"])
            else:
                return make_response(jsonify({"message": "Invalid file!"}), 400)
    return make_response(jsonify({"message": "error"}), 400)


@app.route('/admin/testimonials', methods=['GET', 'POST'])
@login_required("You don't have the user privileges to access this section.")
def get_testimonials():
    """ADMIN Testionials page route

    Returns:
        function: renders page from html jinja template
    """
    form = UpdateForm()
    if request.method == "POST":
        if form.validate_on_submit():
            testimonials = list(mongo.db.testimonials.find())

            for testimonial in testimonials:
                if request.form.get(f"approved[{testimonial['_id']}]"):
                    is_approved = True
                else:
                    is_approved = False
                mongo.db.testimonials.update({"_id": ObjectId(testimonial['_id'])}, {
                    "$set": {"approved": is_approved}})
            flash("Testimonials were successfully updated!", "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_testimonials"))
        else:
            flash("Error submitting the changes!", "danger")

    approved = list(mongo.db.testimonials.find({"approved": True}))
    unapproved = list(mongo.db.testimonials.find({"approved": False}))
    return render_template("admin/testimonials.html", approved=approved, unapproved=unapproved, form=form)


@app.route('/admin/delete_testimonial/<id>')
@login_required("You don't have the user privileges to access this section.")
def delete_testimonial(id):
    """ADMIN Delete testimonial page route

    Args:
        id (string): requested testimonial id

    Returns:
        function: redirects to testimonials page
    """
    mongo.db.testimonials.remove({"_id": ObjectId(id)})
    flash("Testimonial was successfully deleted", "warning")
    return redirect(url_for("get_testimonials"))


@app.route('/admin/blogs')
@login_required("You don't have the user privileges to access this section.")
def get_blogs():
    """ADMIN Blogs page route

    Returns:
        function: renders page from html jinja template
    """
    blogs = list(mongo.db.blogs.find())
    for i, blog in enumerate(blogs):
        blog["body"] = truncate_html(
            blog["body"], 200, end=' [...] ', break_words=True)
        blogs[i] = blog
    return render_template("admin/blogs.html", blogs=blogs)


@app.route('/admin/add_blog', methods=["GET", "POST"])
@login_required("You don't have the user privileges to access this section.")
def add_blog():
    """ADMIN Add Blog page route

    Returns:
        function: renders page from html jinja template
    """
    form = AddBlogForm()
    if request.method == "POST":
        slug_exists = mongo.db.blogs.find_one({"slug": form.slug.data})
        if form.validate_on_submit() and not slug_exists:
            blog = {
                "title": form.title.data,
                "slug": form.slug.data,
                "photos": form.photo_list.data,
                "body": form.body.data,
                "added_on": date.today().strftime("%B %d, %Y")
            }
            mongo.db.blogs.insert_one(blog)
            flash(Markup(
                f"Blog <strong>{blog['title']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_blogs"))
        else:
            if slug_exists:
                flash("This title/slug already exists!", "danger")
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("admin/add_blog.html", form=form)


@ app.route('/admin/edit_blog/<id>', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def edit_blog(id):
    """ADMIN Edit Blog page route

    Args:
        id (string): requested blog id

    Returns:
        function: renders page from html jinja template
    """
    form = EditBlogForm()
    post = mongo.db.blogs.find_one({"_id": ObjectId(id)})
    if request.method == "POST":
        if form.validate_on_submit():
            updated = {
                "title": form.title.data,
                "slug": form.slug.data,
                "body": form.body.data
            }
            flash(Markup(
                f"Blog <strong>{updated['title']}</strong> was successfully edited!"), "success")

            mongo.db.blogs.update({"_id": ObjectId(id)}, {
                "$set": updated})
            # Redirect to avoid re-submission
            return redirect(url_for("get_blogs"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.body.data = post["body"]
    return render_template("admin/edit_blog.html", post=post, form=form)


@ app.route('/admin/delete_blog/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_blog(id):
    """ADMIN Delete Blog page route

    Args:
        id (string): requested blog id

    Returns:
        function: redirects to blogs page
    """
    post = mongo.db.blogs.find_one({"_id": ObjectId(id)})

    photos = list(filter(None, post["photos"].split(',')))
    for photo in photos:
        if photo and os.path.exists(os.path.join(app.config['UPLOAD_PATH'], photo)):
            os.remove(os.path.join(app.config['UPLOAD_PATH'], photo))

    mongo.db.blogs.remove({"_id": ObjectId(id)})
    flash("Blog was successfully deleted", "warning")
    return redirect(url_for("get_blogs"))


@ app.route('/admin/skills', methods=['GET', 'POST'])
@ login_required("You don't have the user privileges to access this section.")
def get_skills():
    """ADMIN Skills page route

    Returns:
        function: renders page from html jinja template
    """
    skills = list(mongo.db.skills.find())
    form = UpdateForm()

    if request.method == "POST":
        if form.validate_on_submit():
            for skill in skills:
                updated = {
                    "name": request.form.get(f"name[{skill['_id']}]"),
                    "percentage": int(request.form.get(f"percentage[{skill['_id']}]"))
                }
                mongo.db.skills.update({"_id": ObjectId(skill['_id'])}, {
                    "$set": updated})

            flash("Skills were successfully updated!", "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_skills"))
        else:
            flash("Error submitting the changes!", "danger")

    return render_template("admin/skills.html", skills=skills, form=form)


@ app.route('/admin/delete_skill/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_skill(id):
    """ADMIN Delete Skill page route

    Args:
        id (string): requested skill id

    Returns:
        function: redirect to skills page
    """
    mongo.db.skills.remove({"_id": ObjectId(id)})
    flash("Skill was successfully deleted", "warning")
    return redirect(url_for("get_skills"))


@ app.route('/admin/add_skill', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def add_skill():
    """ADMIN Add Skill page route

    Returns:
        function: renders page from html jinja template
    """
    form = AddSkillForm()
    if request.method == "POST":
        skill_exists = mongo.db.skills.find_one({"name": form.name.data})
        if form.validate_on_submit() and not skill_exists:
            skill = {
                "name": form.name.data,
                "percentage": int(form.percentage.data)
            }
            mongo.db.skills.insert_one(skill)
            flash(Markup(
                f"Skill <strong>{skill['name']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_skills"))
        else:
            if skill_exists:
                flash("This skill already exists!", "danger")
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("admin/add_skill.html", form=form)


@ app.route('/admin/education', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def get_education():
    """ADMIN Education page route

    Returns:
        function: renders page from html jinja template
    """
    education = list(mongo.db.education.find().sort("order", 1))
    form = UpdateForm()
    if request.method == "POST":
        if form.validate_on_submit():
            for school in education:
                order = request.form.get(f"order[{school['_id']}]")
                if order and (isinstance(order, int) or order.isdigit()):
                    mongo.db.education.update({"_id": ObjectId(school['_id'])}, {
                        "$set": {"order": int(order)}})
                else:
                    flash(Markup(
                        f"School <strong>{school['school']}</strong>: Invalid Order!"), "danger")

            flash("Education successfully updated!", "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_education"))
        else:
            flash("Error submitting the changes!", "danger")

    return render_template("admin/education.html", education=education, form=form)


@ app.route('/admin/add_education', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def add_education():
    """ADMIN Add Education page route

    Returns:
        function: renders page from html jinja template
    """
    form = EducationForm()
    if request.method == "POST":
        if form.validate_on_submit():
            school = {
                "school": form.school.data,
                "period": form.period.data,
                "title": form.title.data,
                "department": form.department.data,
                "description": form.description.data,
                "order": int(form.order.data)
            }
            mongo.db.education.insert_one(school)
            flash(Markup(
                f"School <strong>{school['school']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_education"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.order.data = str(
        mongo.db.education.find_one(sort=[("order", pymongo.DESCENDING)])["order"] + 1)
    form.submit.label.text = "Add"
    return render_template("admin/add_education.html", form=form)


@ app.route('/admin/edit_education/<id>', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def edit_education(id):
    """ADMIN Edit Education page route

    Args:
        id (string): requested education id

    Returns:
        function: renders page from html jinja template
    """
    form = EducationForm()
    school = mongo.db.education.find_one({"_id": ObjectId(id)})
    if request.method == "POST":
        if form.validate_on_submit():
            updated = {
                "school": form.school.data,
                "period": form.period.data,
                "title": form.title.data,
                "department": form.department.data,
                "description": form.description.data,
                "order": int(form.order.data)
            }
            mongo.db.education.update({"_id": ObjectId(id)}, {
                "$set": updated})
            flash(Markup(
                f"School <strong>{updated['school']}</strong> was successfully edited!"), "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_education"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.description.data = school["description"]
    form.submit.label.text = "Edit"
    return render_template("admin/edit_education.html", school=school, form=form)


@ app.route('/admin/delete_education/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_education(id):
    """ADMIN Delete Education page route

    Args:
        id (string): requested education id

    Returns:
        function: redirect to education page
    """
    mongo.db.education.remove({"_id": ObjectId(id)})
    flash("School was successfully deleted")
    return redirect(url_for("get_education"))


@ app.route('/admin/experience', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def get_experience():
    """ADMIN Experience page route

    Returns:
        function: renders page from html jinja template
    """
    experience = list(mongo.db.experience.find().sort("order", 1))
    form = UpdateForm()
    if request.method == "POST":
        if form.validate_on_submit():
            for job in experience:
                order = request.form.get(f"order[{job['_id']}]")
                if order and (isinstance(order, int) or order.isdigit()):
                    mongo.db.experience.update({"_id": ObjectId(job['_id'])}, {
                        "$set": {"order": int(order)}})
                else:
                    flash(Markup(
                        f"Job at <strong>{job['company']}</strong>: Invalid Order"), "danger")

            flash("Work Experience successfully updated!", "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_experience"))
        else:
            flash("Error submitting the changes!", "danger")

    return render_template("admin/experience.html", experience=experience, form=form)


@ app.route('/admin/add_experience', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def add_experience():
    """ADMIN Add Experience page route

    Returns:
        function: renders page from html jinja template
    """
    form = ExperienceForm()
    if request.method == "POST":
        if form.validate_on_submit():
            job = {
                "company": form.company.data,
                "period": form.period.data,
                "role": form.role.data,
                "description": form.description.data,
                "order": int(form.order.data)
            }
            mongo.db.experience.insert_one(job)
            flash(Markup(
                f"Job at <strong>{job['company']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_experience"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.order.data = str(
        mongo.db.experience.find_one(sort=[("order", pymongo.DESCENDING)])["order"] + 1)
    form.submit.label.text = "Add"
    return render_template("admin/add_experience.html", form=form)


@ app.route('/admin/edit_experience/<id>', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def edit_experience(id):
    """ADMIN Edit Experience page route

    Args:
        id (string): requested experience id

    Returns:
        function: renders page from html jinja template
    """
    form = ExperienceForm()
    job = mongo.db.experience.find_one({"_id": ObjectId(id)})
    if request.method == "POST":
        if form.validate_on_submit():
            updated = {
                "company": form.company.data,
                "period": form.period.data,
                "role": form.role.data,
                "description": form.description.data,
                "order": int(form.order.data)
            }
            mongo.db.experience.update({"_id": ObjectId(id)}, {
                "$set": updated})
            flash(Markup(
                f"Job at <strong>{updated['company']}</strong> was successfully edited!"), "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_experience"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.description.data = job["description"]
    form.submit.label.text = "Edit"
    return render_template("admin/edit_experience.html", job=job, form=form)


@ app.route('/admin/delete_experience/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_experience(id):
    """ADMIN Delete Experience page route

    Args:
        id (string): requested experience id

    Returns:
        function: redirect to experience page
    """
    mongo.db.experience.remove({"_id": ObjectId(id)})
    flash("Job was successfully deleted")
    return redirect(url_for("get_experience"))


@ app.route('/admin/projects')
@ login_required("You don't have the user privileges to access this section.")
def get_projects():
    """ADMIN Projects page route

    Returns:
        function: renders page from html jinja template
    """
    projects = list(mongo.db.projects.find())
    return render_template("admin/projects.html", projects=projects)


@ app.route('/admin/add_project', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def add_project():
    """ADMIN Add Project page route

    Returns:
        function: renders page from html jinja template
    """
    form = AddProjectForm()
    if request.method == "POST":
        slug_exists = mongo.db.projects.find_one({"slug": form.slug.data})
        if form.validate_on_submit() and not slug_exists:
            project = {
                "title": form.title.data,
                "slug": form.slug.data,
                "tech": form.tech.data,
                "description": form.description.data,
                "repo": form.repo.data,
                "live_url": form.live_url.data,
                "photos": form.photo_list.data
            }
            mongo.db.projects.insert_one(project)
            flash(Markup(
                f"Project <strong>{project['title']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_projects"))
        else:
            if slug_exists:
                flash("This title/slug already exists!", "danger")
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("admin/add_project.html", form=form)


@ app.route('/admin/edit_project/<id>', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def edit_project(id):
    """ADMIN Edit Project page route

    Args:
        id (string): requested project id

    Returns:
        function: renders page from html jinja template
    """
    form = EditProjectForm()
    project = mongo.db.projects.find_one({"_id": ObjectId(id)})
    if request.method == "POST":
        if form.validate_on_submit():
            updated = {
                "title": form.title.data,
                "slug": form.slug.data,
                "tech": form.tech.data,
                "description": form.description.data,
                "repo": form.repo.data,
                "live_url": form.live_url.data
            }
            mongo.db.projects.update({"_id": ObjectId(id)}, {
                "$set": updated})
            flash(Markup(
                f"Project <strong>{updated['title']}</strong> was successfully edited!"), "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_projects"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.description.data = project["description"]
    return render_template("admin/edit_project.html", project=project, form=form)


@ app.route('/admin/delete_project/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_project(id):
    """ADMIN Delete Project page route

    Args:
        id (string): requested project id

    Returns:
        function: redirect to projects page
    """
    post = mongo.db.projects.find_one({"_id": ObjectId(id)})
    photos = list(filter(None, post["photos"].split(',')))
    for photo in photos:
        if photo and os.path.exists(os.path.join(app.config['UPLOAD_PATH'], photo)):
            os.remove(os.path.join(app.config['UPLOAD_PATH'], photo))

    mongo.db.projects.remove({"_id": ObjectId(id)})
    flash("Project was successfully deleted", "warning")
    return redirect(url_for("get_projects"))


@ app.route('/admin/links', methods=['GET', 'POST'])
@ login_required("You don't have the user privileges to access this section.")
def get_links():
    """ADMIN Links page route

    Returns:
        function: renders page from html jinja template
    """
    links = list(mongo.db.links.find())
    form = UpdateForm()
    if request.method == "POST":
        if form.validate_on_submit():
            for link in links:
                name = request.form.get(f"name[{link['_id']}]")
                icon = request.form.get(f"icon[{link['_id']}]")
                url = request.form.get(f"url[{link['_id']}]")
                url_regex = (
                    r"^[a-z]+://"
                    r"(?P<host>[^\/\?:]+)"
                    r"(?P<port>:[0-9]+)?"
                    r"(?P<path>\/.*?)?"
                    r"(?P<query>\?.*)?$"
                )
                if name and icon and url and re.search(url_regex, url):
                    updated = {
                        "name": name,
                        "icon": icon,
                        "url": url
                    }
                    mongo.db.links.update({"_id": ObjectId(link['_id'])}, {
                        "$set": updated})
                else:
                    if not name:
                        flash(Markup(
                            f"Link <strong>{link['name']}</strong>: Name required"), "danger")
                    if not icon:
                        flash(Markup(
                            f"Link <strong>{link['name']}</strong>: Icon required"), "danger")
                    if not url:
                        flash(Markup(
                            f"Link <strong>{link['name']}</strong>: URL required"), "danger")
                    if not re.search(url_regex, url):
                        flash(Markup(
                            f"Link <strong>{link['name']}</strong>: Invalid URL"), "danger")

            flash("Links were successfully updated!", "success")
            # Redirect to avoid re-submission
            return redirect(url_for("get_links"))
        else:
            flash("Error submitting the changes!", "danger")

    return render_template("admin/links.html", links=links, form=form)


@ app.route('/admin/delete_link/<id>')
@ login_required("You don't have the user privileges to access this section.")
def delete_link(id):
    """ADMIN Delete Link page route

    Args:
        id (string): requested link id

    Returns:
        function: redirect to links page
    """
    mongo.db.links.remove({"_id": ObjectId(id)})
    flash("Link was successfully deleted", "warning")
    return redirect(url_for("get_links"))


@ app.route('/admin/add_link', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def add_link():
    """ADMIN Add Link page route

    Returns:
        function: renders page from html jinja template
    """
    form = AddLinkForm()
    if request.method == "POST":
        if form.validate_on_submit():
            link = {
                "name": form.name.data,
                "icon": form.icon.data,
                "url": form.url.data
            }
            mongo.db.links.insert_one(link)
            flash(Markup(
                f"Link <strong>{link['name']}</strong> was successfully Added!"), "success")
            return redirect(url_for("get_links"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("admin/add_link.html", form=form)


@ app.route('/admin/settings', methods=["GET", "POST"])
@ login_required("You don't have the user privileges to access this section.")
def get_settings():
    """ADMIN Settins page route

    Returns:
        function: renders page from html jinja template
    """
    global settings
    form = SettingsForm()
    if request.method == "POST":
        if form.validate_on_submit():
            updated = {
                "name": form.name.data,
                "bio": form.bio.data,
                "cover": form.cover.data,
                "status": form.status.data,
                "availability": form.availability.data,
                "email": form.email.data,
                "phone": form.phone.data,
                "address": form.address.data,
                "meta_title": form.meta_title.data,
                "meta_desc": form.meta_desc.data,
                "meta_keys": form.meta_keys.data
            }
            mongo.db.settings.update({"_id": ObjectId(settings["_id"])}, {
                "$set": updated})
            flash("Settings were successfully updated!", "success")
            # Update global settings variable
            settings = mongo.db.settings.find_one(
                {"_id": ObjectId(os.environ.get("DB_SETTINGS_ID"))})
            # Redirect to avoid re-submission
            return redirect(url_for("get_settings"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    form.bio.data = settings["bio"]
    form.cover.data = settings["cover"]
    form.meta_desc.data = settings["meta_desc"]
    return render_template("admin/settings.html", form=form)


@ app.route('/admin/login', methods=["GET", "POST"])
def login():
    """ADMIN Login page route

    Returns:
        function: renders page from html jinja template
    """
    form = LoginForm()
    if request.method == "POST":
        if form.validate_on_submit():
            if form.username.data.lower() == os.environ.get("ADMIN_USERNAME").lower() and form.password.data == os.environ.get("ADMIN_PASSWORD"):
                session["user"] = form.username.data.lower()
                flash(f"Welcome, {form.username.data}")
                return redirect(url_for("admin"))
            else:
                # username doesn't exist
                flash("Incorrect Username or Password!", "danger")
                return redirect(url_for("login"))
        else:
            for fieldName, errorMessages in form.errors.items():
                for err in errorMessages:
                    flash(err, "danger")

    return render_template("admin/login.html", form=form)


@ app.route("/admin/logout")
def logout():
    """ADMIN Logout page route

    Returns:
        function: renders page from html jinja template
    """
    if session.get("user"):
        session.pop("user")

    flash("You have been logged out", "danger")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host=os.environ.get("IP"),
            port=int(os.environ.get("PORT")),
            debug=True)
