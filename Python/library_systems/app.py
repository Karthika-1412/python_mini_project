from flask import Flask, render_template, request, redirect, session, g
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE = 'library.db'

# Function to get the database connection
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

# Function to close the database connection after each request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Initialize the database with the required tables
def init_db():
    with app.app_context():
        db = get_db()

        # Check if the 'quantity' column exists and add it if it doesn't
        try:
            db.execute("SELECT quantity FROM books LIMIT 1")
        except sqlite3.OperationalError:
            db.execute("ALTER TABLE books ADD COLUMN quantity INTEGER DEFAULT 0")

        # Create other tables if they don't exist
        db.execute('''CREATE TABLE IF NOT EXISTS admin (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT, password TEXT)''')

        db.execute('''CREATE TABLE IF NOT EXISTS student (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT, password TEXT)''')

        db.execute('''CREATE TABLE IF NOT EXISTS books (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT, author TEXT, quantity INTEGER DEFAULT 0)''')

        db.execute('''CREATE TABLE IF NOT EXISTS borrow_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_username TEXT,
                        book_id INTEGER,
                        borrow_date TEXT)''')

        db.commit()
        print("Database initialized or updated!")

# Route for the homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route for borrowing a book
@app.route('/borrow_book', methods=['POST'])
def borrow_book():
    if 'user' in session and session['role'] == 'student':
        book_id = request.form['book_id']
        db = get_db()
        student_id = db.execute("SELECT id FROM student WHERE username = ?", (session['user'],)).fetchone()[0]
        db.execute("INSERT INTO borrow_history (student_username, book_id, borrow_date) VALUES (?, ?, ?)",
                   (session['user'], book_id, datetime.now().strftime('%Y-%m-%d')))
        db.execute("UPDATE books SET quantity = quantity - 1 WHERE id = ?", (book_id,))
        db.commit()
        return redirect('/student_dashboard')
    return redirect('/')

# Route for student signup
@app.route('/signup/student', methods=['GET', 'POST'])
def signup_student():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        db.execute("INSERT INTO student (username, password) VALUES (?, ?)", (username, password))
        db.commit()
        return redirect('/login/student')
    return render_template('signup_student.html')

# Route for admin signup
@app.route('/signup/admin', methods=['GET', 'POST'])
def signup_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        db.execute("INSERT INTO admin (username, password) VALUES (?, ?)", (username, password))
        db.commit()
        return redirect('/login/admin')
    return render_template('signup_admin.html')

# Route for student login
@app.route('/login/student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM student WHERE username = ? AND password = ?", (username, password)).fetchone()
        if user:
            session['user'] = username
            session['role'] = 'student'
            return redirect('/student_dashboard')
    return render_template('login_student.html')

# Route for admin login
@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute("SELECT * FROM admin WHERE username = ? AND password = ?", (username, password)).fetchone()
        if user:
            session['user'] = username
            session['role'] = 'admin'
            return redirect('/admin_dashboard')
    return render_template('login_admin.html')

# Route for the admin dashboard
@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'user' in session and session['role'] == 'admin':
        db = get_db()

        # Fetch all books and their remaining quantity
        books = db.execute("SELECT * FROM books").fetchall()

        # Fetch the borrow history for each book with student details
        borrow_history = db.execute('''SELECT b.id as book_id, b.title, b.author, bh.student_username, bh.borrow_date
                                       FROM borrow_history bh
                                       JOIN books b ON bh.book_id = b.id
                                       ORDER BY bh.borrow_date DESC''').fetchall()

        # Handling Add/Edit/Delete Book Form Submissions
        if request.method == 'POST':
            if 'add_book' in request.form:
                title = request.form['title']
                author = request.form['author']
                quantity = int(request.form['quantity'])
                db.execute("INSERT INTO books (title, author, quantity) VALUES (?, ?, ?)", (title, author, quantity))
                db.commit()
                return redirect('/admin_dashboard')

            if 'delete_book' in request.form:
                book_id_str = request.form.get('book_id')
                if book_id_str:
                    book_id = int(book_id_str)
                    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
                    db.commit()
                    return redirect('/admin_dashboard')
                else:
                    return "Error: book_id not provided for deletion", 400

            if 'edit_book' in request.form:
                book_id_str = request.form.get('book_id')
                if book_id_str:
                    book_id = int(book_id_str)
                    title = request.form['title']
                    author = request.form['author']
                    quantity = int(request.form['quantity'])
                    db.execute("UPDATE books SET title = ?, author = ?, quantity = ? WHERE id = ?",
                               (title, author, quantity, book_id))
                    db.commit()
                    return redirect('/admin_dashboard')
                else:
                    return "Error: book_id not provided for editing", 400

        return render_template('admin_dashboard.html', user=session['user'], books=books, borrow_history=borrow_history)
    return redirect('/')

# Route for the student dashboard
@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'user' not in session or session['role'] != 'student':
        return redirect('/')

    db = get_db()
    books = []
    if request.method == 'POST':
        if 'search_query' in request.form:
            search_query = request.form['search_query']
            books = db.execute("SELECT * FROM books WHERE title LIKE ?", ('%' + search_query + '%',)).fetchall()

    # Fetch the borrow history for the logged-in student
    history = db.execute('''SELECT b.id as book_id, b.title, b.author, bh.borrow_date 
                            FROM borrow_history bh 
                            JOIN books b ON bh.book_id = b.id 
                            WHERE bh.student_username = ? 
                            ORDER BY bh.borrow_date DESC''', (session['user'],)).fetchall()

    return render_template('student_dashboard.html', user=session['user'], books=books, history=history)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
