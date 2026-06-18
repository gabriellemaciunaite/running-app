from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template("test_form.html")

if __name__ == '__main__':
    # debug=True automatically reloads the server when you save changes
    app.run(debug=True, port=5000)