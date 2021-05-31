// Declare used variables
const formElement = document.getElementById('dropzoneForm');
let formSubmitted = false;
const dropArea = document.getElementById('drop-area');
const fileElem = document.getElementById('drop-file-elem');
const collection = document.getElementById('collection').value;
const docId = document.getElementById('doc-id') ? document.getElementById('doc-id').value : 0;

/** 
* API GET function. Gets the data from the url and sends it as a parameter to the callback function.
* @param {string} method - Request method
* @param {string} url - Api url to be called
* @param {function} cb - Callback function
*/
function apiRequest(method, url, cb, data = undefined) {
    const xhr = new XMLHttpRequest();

    xhr.onreadystatechange = function () {
        if (this.readyState == 4) {
            if (this.status == 200) {
                cb(JSON.parse(this.responseText), this.status);
            } else {
                cb({}, this.status);
            }
        }
    };

    xhr.onerror = function () {
        cb({}, this.status);
    };

    xhr.open(method, url);
    xhr.send(data);
}

/**
* Adds .highlight class to the drop area element.
*/
const highlight = () => {
    dropArea.classList.add('highlight');
}

/**
* Removes .highlight class from the drop area element.
*/
const unhighlight = () => {
    dropArea.classList.remove('highlight');
}

/**
* Updates the hidden input with uploaded filenames list.
*/
const fileListUpdate = () => {
    const fileListInput = document.getElementById('photo_list');
    const fileList = [];
    document.querySelectorAll('.photo-container').forEach(el => {
        fileList.push(el.dataset.src);
    });
    if (fileListInput) fileListInput.value = fileList.join(',');
    if (lightbox) {
        lightbox.reload();
    }
}

/**
* Function called when drop area is clicked and it triggers click on the file input.
*/
const handleClick = () => {
    fileElem.click();
}

/**
 * Handles the dropped files.
* @credit https://www.smashingmagazine.com/2018/01/drag-drop-file-uploader-vanilla-js/
* @param {obj} e - event object.
*/
const handleDrop = (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;

    handleFiles(files);
}

/**
* Handles a set of files by calling Upload function for each.
* If the drag&drop area is not set to multiple, then an ajax DELETE request is sent to delete the current file.
* @param {obj} files - files object.
*/
const handleFiles = (files) => {
    if (dropArea.dataset.multiple == "true") {
        ([...files]).forEach(getSignedRequest);
    } else {
        // check if there is a current file
        if (document.querySelectorAll('.photo-container')[0]) {
            if (confirm('Are you sure?\r\n This will replace the current file!')) {
                const el = document.querySelectorAll('.photo-container')[0];
                deleteFile(el);
            } else {
                return;
            }
        }
        getSignedRequest(files[0]);
    }
}

/** 
* Sends request to AWS S3 server delete url to delete file from cloud
* and calls function to delete file metadata from database deleteFileFromDb
* and removes the image element from DOM
* @param {obj} el - DOM el that contains file metadata and that has to be removed.
*/
const deleteFile = (el) => {
    const fileName = el.dataset.src.split('/').pop();
    const url = urlForDeleteS3 + "?file_name=" + fileName;

    apiRequest("GET", url, (response, status) => {
        if (status === 200) {
            if (docId) {
                deleteFileFromDb(el.dataset.src);
            }
            el.remove();
            fileListUpdate();
            alertToast("Image '" + fileName + "' was successfully deleted!");
        }
        else {
            alertToast("Could not delete.");
        }
    });
}

/** 
* Sends request to python route to get signed request that is then passed through upladFile function
* @param {obj} file - file to be uploaded
*/
const getSignedRequest = (file) => {
    const fileExt = file.name.split('.').pop();
    const date = new Date();
    const newFileName = collection + String(date.getDate()) + String(date.getMonth() + 1) + Math.floor(Math.random() * 999) + '.' + fileExt;
    const renamedFile = new File([file], newFileName, { type: file.type });
    const url = urlForSignS3 + "?file_name=" + renamedFile.name + "&file_type=" + renamedFile.type;

    apiRequest("GET", url, (response, status) => {
        if (status === 200) {
            uploadFile(renamedFile, response.data, response.url);
        }
        else {
            alertToast("Could not get signed URL.");
        }
    });
}

/** 
* Send request to AWS S3 server to upload file
* Calls function to add file to database addFileToDb(url)
* Adds new image element to DOM
* @param {obj} file - File to be uploaded
* @param {array} s3Data - Data from signed request
* @param {string} url - File url from signed request
* @return {ReturnValueDataTypeHere} Brief description of the returning value here.
*/
const uploadFile = (file, s3Data, url) => {
    const postData = new FormData();
    for (key in s3Data.fields) {
        postData.append(key, s3Data.fields[key]);
    }
    postData.append('file', file);

    apiRequest("POST", s3Data.url, (response, status) => {
        if (status === 200 || status === 204) {
            if (docId) {
                addFileToDb(url);
            }
            if (document.getElementById('gallery')) {
                const containerEl = document.getElementById('gallery');
                const existingElCount = document.querySelectorAll(".photo-container").length;
                const imgTag = `<a href="${url}" class="${collection}-gallery">
                                        <img class="img-thumbnail gallery-item" src="${url}" alt="photo">
                                    </a>`;
                const newEl = Object.assign(document.createElement('div'), {
                    className: 'photo-container col-sm-4 col-md-6 col-lg-4',
                    innerHTML: `${imgTag}
                                    <a class="delete-photo btn btn-danger" data-photo-key="${existingElCount}">
                                        <i class="bi bi-trash-fill"></i>
                                    </a>`
                });
                newEl.dataset.src = url;
                containerEl.appendChild(newEl);
                alertToast("Image '" + file.name + "' was successfully uploaded!");
            }
            fileListUpdate();
        }
        else {
            alertToast("Could not upload file.");
        }
    }, postData);
}

/** 
* Sends request to python route to add file to db into specified collection and document
* @param {string} photo - Full url of the photo
*/
const addFileToDb = (photo) => {
    const url = urlForAddPhoto + "?coll=" + collection + "&docid=" + docId + "&photo=" + photo;

    apiRequest("PUT", url, (response, status) => {
        alertToast(response.message)
    });
}

/**
* Sends request to python route to delete file from database
* @param {string} photo - Full url of the photo
*/
const deleteFileFromDb = (photo) => {
    const url = urlForDeletePhoto + "?coll=" + collection + "&photo=" + photo;

    apiRequest("GET", url, (response, status) => {
        alertToast(response.message)
    });
}

/** 
* Generates an array out of dom photos src of a particular class
* for use of image insertion in TinyMCE rich text editor
* @return {array} generated array of photo sources
*/
const getPhotoList = () => {
    if (document.querySelectorAll('.photo-container').length) {
        const photoList = [];
        document.querySelectorAll('.photo-container').forEach((el, i) => {
            photoList.push({ title: 'Photo' + (i + 1), value: el.getElementsByTagName('img')[0].src });
        });

        return photoList;
    } else {
        return [];
    }
}

/**
* Delay function
* @credit https://www.perimeterx.com/tech-blog/2019/beforeunload-and-unload-events/
* @param {number} delay - miliseconds.
*/
const sleep = (delay) => {
    const start = new Date().getTime();
    while (new Date().getTime() < start + delay);
}

// Event Delegation for dynamic created elements
// Click event listener for file delete button
document.getElementById('gallery').addEventListener('click', (e) => {
    if (e.target.classList.contains('delete-photo')) {
        preventDefaults(e);
        if (confirm('Are you sure?\r\n This will delete file and remove it from the database!')) {
            deleteFile(e.target.parentElement);
        }
    }
});

// Event listener for form submission
if (formElement) {
    formElement.addEventListener('submit', () => {
        formSubmitted = true;
    });
}

// Check if db doc id is set (if is set then page is on an edit form)
if (!docId) {
    // Prevent leaving page if any existing uploads (except for submit)
    window.onbeforeunload = () => {
        showSpinner();
        setTimeout(() => { hideSpinner() }, 2000); // Only hides the spinner if user cancels unload
        if (document.querySelectorAll('.photo-container').length && !formSubmitted) {
            return "Are you sure you want to leave?";
        } else {
            return;
        }
    };
    // Delete uploaded files on page unload
    window.onunload = () => {
        if (document.querySelectorAll('.photo-container').length && !formSubmitted) {
            document.querySelectorAll('.photo-container').forEach(el => {
                deleteFile(el);
            });
            sleep(2000);
        }
    };
}

// Drag&Drop event listeners
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});
['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, highlight, false);
});
['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, unhighlight, false);
});
dropArea.addEventListener('drop', handleDrop, false);

// Click on the drag&drop area event listener
dropArea.addEventListener('click', handleClick, false);

// File input change event listener
fileElem.onchange = () => {
    handleFiles(fileElem.files);
    fileElem.value = "";
};