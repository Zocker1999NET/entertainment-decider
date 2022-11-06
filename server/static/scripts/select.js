// custom helper

/**
 * sends a request to the specified url from a form. this will change the window location.
 * @param {string} path the path to send the post request to
 * @param {object} params the parameters to add to the url
 * @param {string} [method=post] the method to use on the form
 * @param {boolean} [redirect=true] should be redirected back to this page (useful for API calls to this app)
 * original source: https://stackoverflow.com/a/133997/4015028
 * - rewrote to use inline helper method prop()
 * - added redirect parameter
 */
function post(path, params, method='post', redirect=true, fragment=null) {
    // The rest of this code assumes you are not using a library.
    // It can be made less verbose if you use one.
    const form = document.createElement('form');
    form.method = method;
    form.action = path;
    function prop(key, value) {
        const hiddenField = document.createElement('input');
        hiddenField.type = 'hidden';
        hiddenField.name = key;
        hiddenField.value = value;
        form.appendChild(hiddenField);
    }
    if (redirect) {
        prop("redirect", window.location.pathname + (fragment !== null ? "#" + fragment : ""));
    }
    for (const key in params) {
        if (params.hasOwnProperty(key)) {
            prop(key, params[key]);
        }
    }
    document.body.appendChild(form);
    form.submit();
}


// select module


function _select_post(path, ids) {
    post(path, {"ids": ids}, "post", true, "media_element_" + ids[0]);
}

const select_sel_checkedBoxes = ".thumbnail_view > input.checkbox[name='element_id']:checked";

function _select_get_ids() {
    return $(select_sel_checkedBoxes).map((_, o) => o.value).toArray();
}

function _select_get_ids_cs() {
    return _select_get_ids().join(",");
}

function select_onChange() {
    const sel_view = "#select_view";
    const sel_counter = sel_view + " .counter";
    const sel_button_clear = sel_view + " button#select_button_clear";
    const sel_button_dependent = sel_view + " button#select_button_clear";
    const element_ids = _select_get_ids();
    if (element_ids.length <= 0) {
        $(sel_view).attr("to_display", "false");
    } else {
        $(sel_button_dependent).prop("disabled", element_ids.length > 1);
        $(sel_view).attr("to_display", "true");
        $(sel_counter).html(element_ids.length);
    }
}

function select_watch() {
    const ids = _select_get_ids();
    _select_post("/api/media/set_watched", ids);
}

function select_ignore() {
    const ids = _select_get_ids();
    _select_post("/api/media/set_ignored", ids);
}

function select_dependent() {
    const ids = _select_get_ids();
    _select_post("/api/media/set_dependent", ids);
}

function select_clear() {
    $(select_sel_checkedBoxes).prop('checked', false);
    select_onChange();
}

$(window).on("load", () => select_onChange());
