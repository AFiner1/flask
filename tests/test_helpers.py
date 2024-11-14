import io
import os

import pytest
import werkzeug.exceptions

import flask
from flask.helpers import get_debug_flag


class FakePath:
    """Fake object to represent a ``PathLike object``.

    This represents a ``pathlib.Path`` object in python 3.
    See: https://www.python.org/dev/peps/pep-0519/
    """

    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return self.path


class PyBytesIO:
    def __init__(self, *args, **kwargs):
        self._io = io.BytesIO(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._io, name)


class TestSendfile:
    def test_send_file(self, app, req_ctx):
        """Test sending a file using Flask's send_file function.

        This test verifies that the send_file function correctly sends a file
        with the expected mimetype and that the file's data matches the expected
        content. It also checks that the direct_passthrough attribute is set
        correctly.
        """
        rv = flask.send_file("static/index.html")
        assert rv.direct_passthrough
        assert rv.mimetype == "text/html"

        with app.open_resource("static/index.html") as f:
            rv.direct_passthrough = False
            assert rv.data == f.read()

        rv.close()

    def test_static_file(self, app, req_ctx):
        """Test sending static files with different cache settings.

        This test checks the behavior of sending static files with and without
        a configured cache max_age. It verifies that the cache control headers
        are set correctly based on the app's configuration and custom logic.
        """
        # Default max_age is None.

        # Test with static file handler.
        rv = app.send_static_file("index.html")
        assert rv.cache_control.max_age is None
        rv.close()

        # Test with direct use of send_file.
        rv = flask.send_file("static/index.html")
        assert rv.cache_control.max_age is None
        rv.close()

        app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600

        # Test with static file handler.
        rv = app.send_static_file("index.html")
        assert rv.cache_control.max_age == 3600
        rv.close()

        # Test with direct use of send_file.
        rv = flask.send_file("static/index.html")
        assert rv.cache_control.max_age == 3600
        rv.close()

        # Test with pathlib.Path.
        rv = app.send_static_file(FakePath("index.html"))
        assert rv.cache_control.max_age == 3600
        rv.close()

        class StaticFileApp(flask.Flask):
            def get_send_file_max_age(self, filename):
                return 10

        app = StaticFileApp(__name__)

        with app.test_request_context():
            # Test with static file handler.
            rv = app.send_static_file("index.html")
            assert rv.cache_control.max_age == 10
            rv.close()

            # Test with direct use of send_file.
            rv = flask.send_file("static/index.html")
            assert rv.cache_control.max_age == 10
            rv.close()

    def test_send_from_directory(self, app, req_ctx):
        """Test sending a file from a directory using send_from_directory.

        This test verifies that the send_from_directory function correctly
        sends a file from a specified directory and that the file's content
        matches the expected data.
        """
        app.root_path = os.path.join(
            os.path.dirname(__file__), "test_apps", "subdomaintestmodule"
        )
        rv = flask.send_from_directory("static", "hello.txt")
        rv.direct_passthrough = False
        assert rv.data.strip() == b"Hello Subdomain"
        rv.close()


class TestUrlFor:
    def test_url_for_with_anchor(self, app, req_ctx):
        """Test URL generation with an anchor.

        This test verifies that the url_for function correctly generates a URL
        with an anchor component, ensuring that the anchor is properly encoded.
        """
        @app.route("/")
        def index():
            return "42"

        assert flask.url_for("index", _anchor="x y") == "/#x%20y"

    def test_url_for_with_scheme(self, app, req_ctx):
        """Test URL generation with a specified scheme.

        This test checks that the url_for function generates an external URL
        with the specified scheme, ensuring that the scheme is correctly applied.
        """
        @app.route("/")
        def index():
            return "42"

        assert (
            flask.url_for("index", _external=True, _scheme="https")
            == "https://localhost/"
        )

    def test_url_for_with_scheme_not_external(self, app, req_ctx):
        """Test URL generation with a scheme without external flag.

        This test verifies that specifying a scheme without the external flag
        raises a ValueError, as the scheme implies an external URL.
        """
        app.add_url_rule("/", endpoint="index")

        # Implicit external with scheme.
        url = flask.url_for("index", _scheme="https")
        assert url == "https://localhost/"

        # Error when external=False with scheme
        with pytest.raises(ValueError):
            flask.url_for("index", _scheme="https", _external=False)

    def test_url_for_with_alternating_schemes(self, app, req_ctx):
        """Test URL generation with alternating schemes.

        This test checks that the url_for function can switch between different
        schemes when generating URLs, ensuring that the scheme is applied correctly
        each time.
        """
        @app.route("/")
        def index():
            return "42"

        assert flask.url_for("index", _external=True) == "http://localhost/"
        assert (
            flask.url_for("index", _external=True, _scheme="https")
            == "https://localhost/"
        )
        assert flask.url_for("index", _external=True) == "http://localhost/"

    def test_url_with_method(self, app, req_ctx):
        """Test URL generation with specific HTTP methods.

        This test verifies that the url_for function can generate URLs for
        endpoints with specific HTTP methods, ensuring that the correct URL
        is generated based on the method.
        """
        from flask.views import MethodView

        class MyView(MethodView):
            def get(self, id=None):
                if id is None:
                    return "List"
                return f"Get {id:d}"

            def post(self):
                return "Create"

        myview = MyView.as_view("myview")
        app.add_url_rule("/myview/", methods=["GET"], view_func=myview)
        app.add_url_rule("/myview/<int:id>", methods=["GET"], view_func=myview)
        app.add_url_rule("/myview/create", methods=["POST"], view_func=myview)

        assert flask.url_for("myview", _method="GET") == "/myview/"
        assert flask.url_for("myview", id=42, _method="GET") == "/myview/42"
        assert flask.url_for("myview", _method="POST") == "/myview/create"

    def test_url_for_with_self(self, app, req_ctx):
        """Test URL generation with 'self' as a variable part.

        This test checks that the url_for function can handle 'self' as a
        variable part in the URL, ensuring that it is correctly replaced with
        the provided value.
        """
        @app.route("/<self>")
        def index(self):
            return "42"

        assert flask.url_for("index", self="2") == "/2"


def test_redirect_no_app():
    """Test redirect function without an app context.

    This test verifies that the redirect function can be used without an
    application context and correctly sets the location and status code.
    """
    response = flask.redirect("https://localhost", 307)
    assert response.location == "https://localhost"
    assert response.status_code == 307


def test_redirect_with_app(app):
    """Test redirect function with an app context.

    This test checks that the redirect function respects the app's custom
    redirect logic when used within an application context.
    """
    def redirect(location, code=302):
        raise ValueError

    app.redirect = redirect

    with app.app_context(), pytest.raises(ValueError):
        flask.redirect("other")


def test_abort_no_app():
    """Test abort function without an app context.

    This test verifies that the abort function raises the correct exceptions
    when used without an application context.
    """
    with pytest.raises(werkzeug.exceptions.Unauthorized):
        flask.abort(401)

    with pytest.raises(LookupError):
        flask.abort(900)


def test_app_aborter_class():
    """Test custom aborter class in a Flask app.

    This test checks that a Flask app can use a custom aborter class, ensuring
    that the app's aborter is an instance of the specified class.
    """
    class MyAborter(werkzeug.exceptions.Aborter):
        pass

    class MyFlask(flask.Flask):
        aborter_class = MyAborter

    app = MyFlask(__name__)
    assert isinstance(app.aborter, MyAborter)


def test_abort_with_app(app):
    """Test abort function with a custom error code in an app context.

    This test verifies that the abort function can handle custom error codes
    when used within an application context, raising the appropriate exception.
    """
    class My900Error(werkzeug.exceptions.HTTPException):
        code = 900

    app.aborter.mapping[900] = My900Error

    with app.app_context(), pytest.raises(My900Error):
        flask.abort(900)


class TestNoImports:
    """Test Flasks are created without import.

    Avoiding ``__import__`` helps create Flask instances where there are errors
    at import time.  Those runtime errors will be apparent to the user soon
    enough, but tools which build Flask instances meta-programmatically benefit
    from a Flask which does not ``__import__``.  Instead of importing to
    retrieve file paths or metadata on a module or package, use the pkgutil and
    imp modules in the Python standard library.
    """

    def test_name_with_import_error(self, modules_tmp_path):
        """Test Flask app creation with an import error.

        This test verifies that creating a Flask app with a module that raises
        an import error does not cause the app creation to fail, ensuring that
        Flask does not import the module during initialization.
        """
        (modules_tmp_path / "importerror.py").write_text("raise NotImplementedError()")
        try:
            flask.Flask("importerror")
        except NotImplementedError:
            AssertionError("Flask(import_name) is importing import_name.")


class TestStreaming:
    def test_streaming_with_context(self, app, client):
        """Test streaming response with request context.

        This test verifies that a streaming response can access the request
        context, ensuring that request data is available during streaming.
        """
        @app.route("/")
        def index():
            def generate():
                yield "Hello "
                yield flask.request.args["name"]
                yield "!"

            return flask.Response(flask.stream_with_context(generate()))

        rv = client.get("/?name=World")
        assert rv.data == b"Hello World!"

    def test_streaming_with_context_as_decorator(self, app, client):
        """Test streaming response with context as a decorator.

        This test checks that the stream_with_context decorator allows a
        generator function to access the request context during streaming.
        """
        @app.route("/")
        def index():
            @flask.stream_with_context
            def generate(hello):
                yield hello
                yield flask.request.args["name"]
                yield "!"

            return flask.Response(generate("Hello "))

        rv = client.get("/?name=World")
        assert rv.data == b"Hello World!"

    def test_streaming_with_context_and_custom_close(self, app, client):
        """Test streaming response with custom close method.

        This test verifies that a streaming response can use a custom close
        method, ensuring that the close method is called after streaming.
        """
        called = []

        class Wrapper:
            def __init__(self, gen):
                self._gen = gen

            def __iter__(self):
                return self

            def close(self):
                called.append(42)

            def __next__(self):
                return next(self._gen)

            next = __next__

        @app.route("/")
        def index():
            def generate():
                yield "Hello "
                yield flask.request.args["name"]
                yield "!"

            return flask.Response(flask.stream_with_context(Wrapper(generate())))

        rv = client.get("/?name=World")
        assert rv.data == b"Hello World!"
        assert called == [42]

    def test_stream_keeps_session(self, app, client):
        """Test streaming response retains session data.

        This test checks that a streaming response retains access to session
        data, ensuring that session modifications persist during streaming.
        """
        @app.route("/")
        def index():
            flask.session["test"] = "flask"

            @flask.stream_with_context
            def gen():
                yield flask.session["test"]

            return flask.Response(gen())

        rv = client.get("/")
        assert rv.data == b"flask"


class TestHelpers:
    @pytest.mark.parametrize(
        ("debug", "expect"),
        [
            ("", False),
            ("0", False),
            ("False", False),
            ("No", False),
            ("True", True),
        ],
    )
    def test_get_debug_flag(self, monkeypatch, debug, expect):
        """Test retrieval of the Flask debug flag from environment.

        This test verifies that the get_debug_flag function correctly retrieves
        the Flask debug flag from the environment, interpreting various string
        representations of boolean values.
        """
        monkeypatch.setenv("FLASK_DEBUG", debug)
        assert get_debug_flag() == expect

    def test_make_response(self):
        """Test creation of a response object.

        This test checks that the make_response function creates a response
        object with the expected status code and mimetype, and that it can
        handle different types of input data.
        """
        app = flask.Flask(__name__)
        with app.test_request_context():
            rv = flask.helpers.make_response()
            assert rv.status_code == 200
            assert rv.mimetype == "text/html"

            rv = flask.helpers.make_response("Hello")
            assert rv.status_code == 200
            assert rv.data == b"Hello"
            assert rv.mimetype == "text/html"

    @pytest.mark.parametrize("mode", ("r", "rb", "rt"))
    def test_open_resource(self, mode):
        """Test opening a resource file in various modes.

        This test verifies that the open_resource function can open a resource
        file in different read modes, ensuring that the file's content is
        correctly read.
        """
        app = flask.Flask(__name__)

        with app.open_resource("static/index.html", mode) as f:
            assert "<h1>Hello World!</h1>" in str(f.read())

    @pytest.mark.parametrize("mode", ("w", "x", "a", "r+"))
    def test_open_resource_exceptions(self, mode):
        """Test exceptions raised by open_resource with invalid modes.

        This test checks that the open_resource function raises a ValueError
        when attempting to open a resource file in write or append modes, which
        are not supported.
        """
        app = flask.Flask(__name__)

        with pytest.raises(ValueError):
            app.open_resource("static/index.html", mode)
