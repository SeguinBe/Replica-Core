/**
 * Created by benoit on 18/01/2016.
 */

var replicaModule = angular.module('replicaModule', [
    'mrImage', 'ui.router', 'ngMaterial', 'ngCookies', 'ngMessages',
    'naif.base64', 'satellizer', 'angular-inview', 'hl.sticky',
    'angulartics', 'angulartics.google.analytics']);

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
            url: "/search?q&n&image_url&index&expmode",
            templateUrl: "partials/search.html",
            reloadOnSearch: false,
            params: {
                q: null,
                n: null,
                image_url: null,
                index: null,
                expmode: null
            },
            resolve: {
                loginRequired: loginRequired
            }
        })
        .state('proposals-list', {
            controller: 'proposalsListController',
            url: "/proposals-list",
            templateUrl: "partials/proposals_list.html",
            resolve: {
                loginRequired: loginRequired
            }
        })
        .state('groups-list', {
            controller: 'groupsListController',
            url: "/groups-list",
            templateUrl: "partials/groups_list.html",
            resolve: {
                loginRequired: loginRequired
            }
        })
        .state('group', {
            controller: 'groupEditController',
            url: "/group/{groupUid}",
            templateUrl: "partials/group_edit.html",
        })
        .state('graph', {
            controller: 'graphController',
            url: "/graph/{groupUid}",
            templateUrl: "partials/graph.html"
        })
        .state('stats', {
            controller: 'statsController',
            url: "/stats",
            templateUrl: "partials/stats.html"
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
    $scope.getImageThumbnail2 = function(e) {
        return e.iiif_url + "/full/450,/0/default.jpg";
    };
    $scope.getImage = function (e) {
        return e.images[0].iiif_url + "/full/!1000,1000/0/default.jpg";
    };
    $scope.getImage2 = function (e) {
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
                rootScope: $scope
                //getImage: $scope.getImage
            },
            parent: angular.element(document.body),
            targetEvent: ev,
            clickOutsideToClose: true,
            fullscreen: true,
            multiple: true
        });

        function DialogController($scope, $mdDialog, locals, rootScope) {
            $scope.getImage = function (e) {
                if (e != undefined)
                    return e.iiif_url + "/full/!1000,1000/0/default.jpg";
                else
                    return "";
            };
            $scope.locals = locals;
            $scope.element = null;
            $scope.showImageDialog = rootScope.showImageDialog;
            $http.get('api/image/'+locals.image_uid).then(
            function (response) {
                $scope.element = response.data;
            }, function (response) {
                $scope.showSimpleToast("Unable to fetch image details : " + response.status + " " + response.data);
            });
        }
    };

    $scope.$on('showImageDialog', function(evt, uid) {
        $scope.showImageDialog(null, uid);
      });

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

    $scope.getUsername = function() {
        return $auth.getPayload().username;
    };

    $scope.getUserUid = function() {
        return $auth.getPayload().user_uid;
    };

    $scope.getAuthorizationLevel = function() {
        return $auth.getPayload().authorization_level;
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
    $scope.annotateProposal = function (i) {
        $mdDialog.show({
            template: '<md-dialog>' +

            '  <md-dialog-content>Positive Link Type?</md-dialog-content>' +
            '  <div flex="row">' +
            '       <img-box element="link.img1" display-size="200"></img-box>' +
            '       <img-box element="link.img2" display-size="200"></img-box>' +
            '   <md-divider></md-divider>' +
            '   </div>' +
            '  <md-dialog-actions>' +
            '    <md-button ng-click="closeDialog(type)" class="md-primary" ng-repeat="type in POSSIBLE_TYPES">' +
            '      {{type}}' +
            '    </md-button>' +
            '    <md-button ng-click="cancelDialog()" class="md-secondary">' +
            '      Cancel' +
            '    </md-button>' +
            '  </md-dialog-actions>' +
            '</md-dialog>',
            locals: { rootScope: $scope },
            controller: function ($mdDialog, $scope, rootScope) {
                $scope.POSSIBLE_TYPES = ['DUPLICATE', 'POSITIVE', 'NEGATIVE'];
                $scope.link = {
                    img1: rootScope.proposalsList[i].images[0],
                    img2: rootScope.proposalsList[i].images[1]
                };
                $scope.closeDialog = function (link_type) {
                    $mdDialog.hide({link: $scope.link, link_type: link_type});
                    // Remove from display
                    rootScope.proposalsList.splice(i,1);
                };
                $scope.cancelDialog = function () {
                    $mdDialog.cancel();
                }
            }
        }).then(
            function (data) {
                var link = data.link;
                var link_type = data.link_type;

                $http.post('api/link/create', {
                        img1_uid: link.img1.uid, img2_uid: link.img2.uid,
                        type: data.link_type
                    }
                ).then(function () {
                        $scope.showSimpleToast(link_type + " link save success.");
                    }
                    , function (response) {
                        $scope.showSimpleToast(link_type + " link save error.");
                    });
            })
    };
    $scope.refreshProposals();
});


replicaModule.controller('groupsListController', function ($scope, $http, $mdDialog, $cookies, $mdToast, $state) {
    $scope.groups = [];
    $scope.refreshGroups = function () {
        $http.get('api/user/groups').then(
            function (response) {
                $scope.groups = response.data.groups;
            }, function (response) {
                $scope.showErrorToast("Fetching groups failed", response);
            });
    };
    $scope.deleteGroup = function (group_uid) {
        $scope.confirmDialog('Delete', 'Are you sure you want to delete this group?').then(
            function () {
                $http.delete('api/group/'+group_uid).then(
                function (response) {
                    $scope.alertDialog('Alert', 'Group deleted');
                    $scope.refreshGroups();
                }, function (response) {
                    $scope.showErrorToast("Delete operation failed", response);
            });
            }
        );
    };
    $scope.refreshGroups();
});

replicaModule.controller('groupEditController', function ($scope, $http, $mdDialog, $cookies,
                                                          $mdToast, $state, $stateParams) {
    $scope.groupUid = $stateParams.groupUid;
    $scope.groupData = {};
    $scope.refreshGroup = function () {
        $http.get('api/group/'+$scope.groupUid).then(
            function (response) {
                $scope.groupData = response.data;
            }, function (response) {
                $scope.showErrorToast("Fetching group failed", response);
            });
    };
    $scope.removeFromSelection = function (item, sel) {
        for (var n = 0; n < sel.length; n++) {
            if (sel[n].uid == item.uid) {
                sel.splice(n, 1);
                break;
            }
        }
    };
    $scope.isOwner = function() {
        return $scope.groupData.owner.uid == $scope.getUserUid();
    };
    $scope.saveGroup = function() {
        $http.put('api/group/'+$scope.groupUid,
            {
                label: $scope.groupData.label,
                notes: $scope.groupData.notes,
                image_uids: $scope.groupData.images.map(function (i) { return i.uid;})
            }
        ).then(
            function (response) {
                $scope.showSimpleToast('Saving success');
            }, function (response) {
                $scope.showErrorToast("Saving failed", response);
            });
    };
    $scope.refreshGroup();
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


replicaModule.controller('screenSaverController', function ($interval, $scope, $http, preloader) {
    $scope.elements = [];
    $scope.currentSelection = [];
    $scope.negativeSelection = [];

    function getImageThumbnail(e) {
        return e.images[0].iiif_url + "/full/450,/0/default.jpg";
    }

    var reloadElements = function () {
        $http.get('api/element/random').then(
            function (response) {
                var query = response.data[0];
                var request = {
                    "positive_image_uids": [query.images[0].uid],
                    "negative_image_uids": [],
                    "nb_results": 50
                };
                $http.post("/api/image/search", request).then(
                    function (response) {
                        var elements = response.data.results;
                        preloader.preloadImages( elements.map(getImageThumbnail) )
                        .then(function() {
                            $scope.elements = elements;
                        },
                        function() {
                            // Loading failed on at least one image.
                        });

                    }, function (response) {
                        $scope.showErrorToast("Search failed", response);
                    }
                )
            }, function (response) {
                $scope.showErrorToast("Random fetching failed",  response);
            });
    };

    $interval(reloadElements, 10000);

});