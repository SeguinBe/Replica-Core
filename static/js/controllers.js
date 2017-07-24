/**
 * Created by benoit on 18/01/2016.
 */

var imageServerAdress = 'http://dhlabsrv4.epfl.ch/iiif_replica/';

var replicaModule = angular.module('replicaModule', [
    'mrImage', 'ui.router', 'ngMaterial', 'ngCookies', 'ngMessages',
    'naif.base64', 'satellizer', 'angular-inview', 'hl.sticky']);

replicaModule.config(function ($stateProvider, $urlRouterProvider, $authProvider) {

    $authProvider.loginUrl = '/api/auth';
    //
    // For any unmatched url, redirect to /search
    $urlRouterProvider.otherwise("/search");
    //
    // Now set up the states
    $stateProvider
        .state('search', {
            controller: 'searchController',
            url: "/search?q&n&image_url",
            templateUrl: "partials/search.html",
            reloadOnSearch: false,
            params: {
                q: null,
                n: null,
                image_url: null
            }
        })
        .state('proposals-list', {
            controller: 'proposalsListController',
            url: "/proposals-list",
            templateUrl: "partials/proposals_list.html"
        })
        .state('annotation', {
            controller: 'annotationEditController',
            url: "/annotation?id",
            templateUrl: "partials/annotation.html",
            params: {
                id: null
            }
        })
        .state('graph', {
            controller: 'graphController',
            url: "/graph?uid",
            templateUrl: "partials/graph.html",
            params: {
                uid: null
            }
        })
        .state('stats', {
            controller: 'statsController',
            url: "/stats",
            templateUrl: "partials/stats.html"
        })
        .state('upload', {
            controller: 'uploadImageController',
            url: "/upload",
            templateUrl: "partials/upload.html",
            resolve: {
                loginRequired: loginRequired
            }
        })
        .state('login', {
            controller: 'loginController',
            url: "/login",
            templateUrl: "partials/login.html",
            resolve: { //Function to check if user is already logged in
                //skipIfLoggedIn: skipIfLoggedIn
            }
        })
        .state('state2.list', {
            url: "/list",
            templateUrl: "partials/state2.list.html",
            controller: function ($scope) {
                $scope.things = ["A", "Set", "Of", "Things"];
            }
        });

    //If a user is already logged in, the Login window if requested need not be displayed.
    function skipIfLoggedIn($q, $auth) {
        var deferred = $q.defer();
        if ($auth.isAuthenticated()) {
            deferred.reject();
        } else {
            deferred.resolve();
        }
        return deferred.promise;
    }

    function loginRequired($q, $location, $auth, $state) {
        var deferred = $q.defer();
        if ($auth.isAuthenticated()) {
            deferred.resolve();
        } else {
            $location.path('/login');

        }
        return deferred.promise;

    }
});

replicaModule.controller('mainController', function ($scope, $http, $mdDialog, $mdToast, $auth, $location, $state) {
    $scope.getImageThumbnail = function(e) {
        return e.images[0].iiif_url + "/full/450,/0/default.jpg";
    };
    $scope.getImage = function (e) {
        return e.images[0].iiif_url + "/full/!1000,1000/0/default.jpg";
    };
    $scope.showSimpleToast = function (text) {
        $mdToast.show(
            $mdToast.simple()
                .hideDelay(3000)
                .position("top right")
                .textContent(text)
        );
    };
    $scope.showErrorToast = function (text, response) {
        $mdToast.show(
            $mdToast.simple()
                .hideDelay(4000)
                .position("top right")
                .textContent(text + ' : <'+ response.status + '> '+response.data.message)
        );
    };

    $scope.confirmDialog = function(title, textContent) {
        return $mdDialog.show(
            $mdDialog.confirm()
                .parent(angular.element(document.body))
                .clickOutsideToClose(true)
                .title(title)
                .textContent(textContent)
                .ariaLabel('Confirm Dialog')
                .ok('Confirm')
                .cancel('Cancel')
        );
    };

    $scope.alertDialog = function(title, textContent) {
        return $mdDialog.show(
            $mdDialog.alert()
                .parent(angular.element(document.body))
                .clickOutsideToClose(true)
                .title(title)
                .textContent(textContent)
                .ariaLabel('Alert Dialog')
                .ok('OK')
        );
    };

    $scope.showImageDialog = function (ev, image_uid) {
        $mdDialog.show({
            controller: DialogController,
            templateUrl: 'dialog/image_dialog.tmpl.html',
            locals: {
                image_uid: image_uid,
                //getImage: $scope.getImage
            },
            parent: angular.element(document.body),
            targetEvent: ev,
            clickOutsideToClose: true,
            fullscreen: true,
            multiple: true
        });

        function DialogController($scope, $mdDialog, locals) {
            $scope.getImage = function (e) {
                if (e != undefined)
                    return e.iiif_url + "/full/!1000,1000/0/default.jpg";
                else
                    return "";
            };
            $scope.locals = locals;
            $scope.element = null;
            $http.get('api/image/'+locals.image_uid).then(
            function (response) {
                $scope.element = response.data;
            }, function (response) {
                $scope.showSimpleToast("Unable to fetch image details : " + response.status + " " + response.data);
            });
        }
    };

    $scope.showCropperDialog = function (ev, element) {
        /**
         * Needs to be called with element as an image object (with a iiif_url field)
         */
        $mdDialog.show({
            controller: DialogController,
            templateUrl: 'dialog/cropper_dialog.tmpl.html',
            locals: {
                element: element
            },
            parent: angular.element(document.body),
            targetEvent: ev,
            clickOutsideToClose: true,
            fullscreen: true
        }).then(function(answer) {
            console.log(answer);
            element.box=answer;
        }, function() {
        });
        function DialogController($scope, $mdDialog, locals) {
            $scope.locals = locals;

            $scope.image = {
                src: $scope.locals.element.iiif_url + "/full/!1000,1000/0/default.jpg",
                maxWidth: 480
            };

            $scope.selector = {};

            $scope.drawer = [];

            $scope.validateSelection= function() {
                $mdDialog.hide({  // close the dialog and send back the answer
                    'x': $scope.selector.p_x1,
                    'y': $scope.selector.p_y1,
                    'w': $scope.selector.p_x2-$scope.selector.p_x1,
                    'h': $scope.selector.p_y2-$scope.selector.p_y1
                });
            }
        }
    };

    $scope.isAuthenticated = function() {
        return $auth.isAuthenticated();
    };

    $scope.logOut = function() {
        if (!$auth.isAuthenticated()) { return; }
        $auth.logout()
            .then(function() {
                $location.url('/');
            });
    };

    $scope.getIdList = function(arr) {
        var idList = [];
        for (var n = 0; n < arr.length; n++)
            idList.push(arr[n].uid);
        return idList;
    };

    $scope.isInSelection = function (item, sel) {
        return !sel.every(function (e) {
            return item.uid != e.uid
        });
    };
});

replicaModule.controller('proposalsListController', function ($scope, $http, $mdDialog, $cookies, $mdToast, $state) {
    $scope.proposalsList = [];
    $scope.refreshProposals = function () {
        $http.get('api/link/proposal/random', {nb_proposals:50}).then(
            function (response) {
                $scope.proposalsList = response.data;
            }, function (response) {
                $scope.showErrorToast("Fetching list failed", response);
            });
    };
    $scope.refreshProposals();
});


/*replicaModule.controller('annotationEditController', function ($scope, $http, $mdDialog, $cookies, $mdToast, $state, $stateParams) {
    $scope.annotationId = $stateParams.id;

    $scope.annotationData = {
        label: 'Loading...',
        elements: [],
        id: 'Loading...'
    };

    function loadAnnotation(uuid) {
        $http.get('api/v1/annotation/id/'+uuid).then(
            function (response) {
                $scope.annotationData = response.data;
            }, function (response) {
                $scope.showSimpleToast("Error retrieving data : " + response.status + " " + response.data.message);
            });
    }

    loadAnnotation($scope.annotationId);

    $scope.deleteAnnotation = function (uuid) {
        $scope.confirmDialog("Confirmation", "You are going to delete this annotation. Are you sure?").then(
            function() {
                $http.delete('api/v1/annotation/id/' + $scope.annotationId).then(
                    function (response) {
                        $scope.alertDialog("Annotation deletion success : " + $scope.annotationId)
                            .then(function() {
                                $state.go('search');
                            });

                    }, function (response) {
                        $scope.alertDialog("Annotation deletion failed : " + response.status, response.data.message);
                    });
            }
        );
    };

    $scope.saveAnnotation = function (uuid) {
        console.log("saving;...");
        $scope.confirmDialog("Confirmation", "Are you sure you want to modify this annotation?").then(
            function() {
                $http.put('api/v1/annotation/id/' + $scope.annotationId,
                    {
                        id: $scope.annotationData.id,
                        label: $scope.annotationData.label,
                        ids: $scope.getIdList($scope.annotationData.elements)
                    }
                ).then(
                    function (response) {
                        $scope.alertDialog("Save success : " + $scope.annotationId);
                    }, function (response) {
                        $scope.alertDialog("Annotation save failed : " + response.status, response.data.message);
                    });
            }
        );
    };

    $scope.addImagePrompt = function () {
        $mdDialog.show(
            $mdDialog.prompt()
                .title("Id of the image to be added")
                .placeholder("id")
                .ok('OK')
                .cancel('Cancel')
        ).then(
            function (uuid) {
                $http.get('api/v1/database/id/'+uuid).then(
                    function (response) {
                        $scope.annotationData.elements.push(response.data);
                    }, function (response) {
                        $scope.showSimpleToast("Error retrieving data : " + response.status + " " + response.data.message);
                    });
            }
        )
    };

    $scope.removeFromSelection = function (item, sel) {
        for (var n = 0; n < sel.length; n++) {
            if (sel[n].id == item.id) {
                sel.splice(n, 1);
                break;
            }
        }
    };
});


/*replicaModule.controller('uploadImageController', function ($scope, $http, $mdDialog, $cookies, $mdToast) {
    $scope.metadata_fields = [
        {key : 'title', value : ""},
        {key : 'author', value : ""},
        {key : 'date', value : ""}
    ];
    $scope.origin = "web-upload";
    $scope.image_url="";
    $scope.webpage_url="";
    $scope.image_file={};

    $scope.uploadImage = function () {
        var request = {
            "origin": $scope.origin,
            "image_url": $scope.image_url,
            "webpage_url": $scope.webpage_url,
            "image_data": $scope.image_file.base64,
            "metadata": {}
        };
        for (var i = 0; i < $scope.metadata_fields.length; i++) {
            request.metadata[$scope.metadata_fields[i].key] = $scope.metadata_fields[i].value;
        }
        console.log(request);
        $http.post('api/v1/database', request).then(
            function (response) {
                console.log(response.data);
                $scope.showSimpleToast("Upload successful : 'id'=" + response.data.id);
            }, function (response) {
                console.log(response.data);
                $scope.showSimpleToast("Upload failed : " + response.status + " " + response.data.message);
            });

    };
});*/

replicaModule.controller('loginController', function ($scope, $http, $mdDialog, $cookies, $mdToast, $auth, $state) {
    $scope.username = "";
    $scope.password = "";

    $scope.login = function() {
        credentials = {
            username: $scope.username,
            password_sha256: sha256($scope.password)
        };

        // Use Satellizer's $auth.login method to verify the username and password
        $auth.login(credentials).then(function(data) {
                // If login is successful, redirect to users list
                $state.go('search');
            })
            .catch(function(response) { // If login is unsuccessful, display relevant error message.
                $scope.showSimpleToast("Login failed :" + response.data);
            });
    };
});


replicaModule.controller('statsController', function ($scope, $http, $mdDialog, $cookies, $mdToast, $auth, $state) {
    $scope.stats = [];

    $scope.refreshStats = function () {
        $http.get('api/stats').then(
            function (response) {
                $scope.stats = response.data.stats;
            }, function (response) {
                $scope.showErrorToast("Stats fetching failed",  response);
            });
    };
    $scope.refreshStats();
});