
replicaModule.controller('searchController', function ($scope, $http, $mdDialog, $cookies, $state, $stateParams, $analytics) {
    $scope.results = [];
    $scope.showSideQuery = true;
    $scope.showResultsAsEmbedding = false;
    $scope.nbResults = 100;
    var resultsDisplayedInitial = 16;
    console.log($stateParams);
    if ($stateParams.q != null || $stateParams.n != null || $stateParams.image_url != null) {
        $scope.current_selection = [];
        $scope.negative_selection = [];
        loadElementsFromIdList(parseParams($stateParams.q), $scope.current_selection);
        loadElementsFromIdList(parseParams($stateParams.n), $scope.negative_selection);
        //loadElementsFromUrlList(parseParams($stateParams.image_url), $scope.current_selection);
    } else {
        loadCookies();
    }
    $scope.searchText = function () {
        var request = {
            query: $scope.searchQuery,
            nb_results: $scope.nbResults
        };
        $http.get('api/search/text',
            {params: request}).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
            }, function (response) {
                $scope.showErrorToast("Search failed", response);
            }).finally(
            function () {
                $analytics.eventTrack('searchText');
                logEvent('search_text', request);
            }
        )
    };
    $scope.is_searching = false;
    $scope.searchImage = function () {
        $scope.is_searching = true;
        var positive_image_ids = [];
        for (var i = 0; i < $scope.current_selection.length; i++)
            positive_image_ids.push($scope.current_selection[i].images[0].uid);
        var negative_image_ids = [];
        for (i = 0; i < $scope.negative_selection.length; i++)
            negative_image_ids.push($scope.negative_selection[i].images[0].uid);
        var request = {
            "positive_image_uids": positive_image_ids,
            "negative_image_uids": negative_image_ids,
            "nb_results": $scope.nbResults
        };
        $http.post("/api/image/search", request).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
            }, function (response) {
                $scope.showErrorToast("Search failed", response);
            }
        ).finally(
            function () {
                $scope.is_searching=false;
                $analytics.eventTrack('searchImage');
                logEvent('search_image', request);
            }
        );
    };
    $scope.searchImageRegion = function () {
        $scope.is_searching = true;
        var request = {
            "image_uid": $scope.current_selection[0].images[0].uid,
            "box_x": $scope.current_selection[0].images[0].box.x,
            "box_y": $scope.current_selection[0].images[0].box.y,
            "box_h": $scope.current_selection[0].images[0].box.h,
            "box_w": $scope.current_selection[0].images[0].box.w,
            "nb_results": $scope.nbResults,
            "reranking_results": 4000
        };
        $http.post("/api/image/search_region", request).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
                $scope.showResultsAsEmbedding = false;
            }, function (response) {
                $scope.showErrorToast("Search failed", response.status);
            }
        ).finally(
            function () {
                $scope.is_searching=false;
                $analytics.eventTrack('searchImageRegion');
                logEvent('search_region', request);
            }
        );
    };
    $scope.showMoreResults = function () {
        $scope.resultsDisplayed += resultsDisplayedInitial;
    };
    $scope.addAnnotation = function () {
        $mdDialog.show({
            template: '<md-dialog>' +

            '  <md-dialog-content>Positive Link Type?</md-dialog-content>' +

            '  <md-dialog-actions>' +
            '    <md-button ng-click="closeDialog(type)" class="md-primary" ng-repeat="type in POSSIBLE_TYPES">' +
            '      {{type}}' +
            '    </md-button>' +
            '    <md-button ng-click="cancelDialog()" class="md-secondary">' +
            '      Cancel' +
            '    </md-button>' +
            '  </md-dialog-actions>' +
            '</md-dialog>',
            controller: function ($mdDialog, $scope) {
                $scope.POSSIBLE_TYPES = ['DUPLICATE', 'POSITIVE'];
                $scope.closeDialog = function (link_type) {
                    $mdDialog.hide(link_type);
                };
                $scope.cancelDialog = function () {
                    $mdDialog.cancel();
                }
            }
        }).then(
            function(link_type) {
                $mdDialog.show({
                    template: '<md-dialog>' +
                    '  <md-dialog-content>' +
                    '   <h3>Here are the {{ links.length }} links that will be added</h3>' +
                    '   <div flex="row" ng-repeat="link in links">' +
                    '       <img-box element="link.img1" display-size="200"></img-box>' +
                    '       <img-box element="link.img2" display-size="200"></img-box>' +
                    '       <span>{{ link.type }}</span>' +
                    '       <span>{{ link.status }}</span>' +
                    '   <md-divider></md-divider>' +
                    '   </div>' +
                    '</md-dialog-content>' +
                    '  <md-dialog-actions>' +
                    '    <md-button ng-click="saveAll()" class="md-primary" ng-disabled="saving_started">' +
                    '      Save All' +
                    '    </md-button>' +
                    '    <md-button ng-click="closeDialog()" class="md-primary">' +
                    '      Close' +
                    '    </md-button>' +
                    '  </md-dialog-actions>' +
                    '</md-dialog>',
                    locals: { rootScope: $scope },
                    controller: function ($http, $mdDialog, $scope, rootScope) {
                        $scope.saving_started = false;
                        // Generate links
                        $scope.links = [];
                        for (var n = 0; n < rootScope.current_selection.length; n++) {
                            for (var m = 0; m < n; m++) {
                                $scope.links.push({
                                    img1: rootScope.current_selection[n].images[0],
                                    img2: rootScope.current_selection[m].images[0],
                                    type: link_type,
                                    status: ""})
                            }
                        }
                        for (var n = 0; n < rootScope.current_selection.length; n++) {
                            for (var m = 0; m < rootScope.negative_selection.length; m++) {
                                $scope.links.push({
                                    img1: rootScope.current_selection[n].images[0],
                                    img2: rootScope.negative_selection[m].images[0],
                                    type: 'NEGATIVE',
                                    status: ""})
                            }
                        }
                        // Saving functions
                        for (var n = 0; n < $scope.links.length; n++) {
                            $scope.links[n].create = function() {
                                this.status = 'SENDING';
                                var l = this;
                                $http.post('api/link/create', {
                                    img1_uid: this.img1.uid, img2_uid: this.img2.uid,
                                    type: this.type}
                                ).then(function() {
                                        l.status = 'ADDED';
                                    }
                                , function(response) {
                                    l.status = 'ERROR : ' + response.data.message;
                                })
                            };
                        }
                        $scope.closeDialog = function() {
                            $mdDialog.hide();
                        };
                        $scope.saveAll = function() {
                            $scope.saving_started = true;
                            for (var i = 0; i < $scope.links.length; i++) {
                                $scope.links[i].create();
                            }
                        };
                    }
                });
            }
        );
    };
    $scope.addToSelection = function (item, sel) {
        if (!$scope.isInSelection(item, sel)) {
            sel.push(item);
            logEvent('add_selection');
        }
        updateCookies();
        updateState();
    };
    $scope.$on('toggleCurrentSelection', function(evt, d) {
        if ($scope.isInSelection(d, $scope.negative_selection))
            return;
        $scope.$apply(function () {
            if ($scope.isInSelection(d, $scope.current_selection))
                $scope.removeFromSelection(d, $scope.current_selection);
            else
                $scope.addToSelection(d, $scope.current_selection);
      })
    });
    $scope.$on('toggleNegativeSelection', function(evt, d) {
        if ($scope.isInSelection(d, $scope.current_selection))
            return;
        $scope.$apply(function () {
        if ($scope.isInSelection(d, $scope.negative_selection))
            $scope.removeFromSelection(d, $scope.negative_selection);
        else
            $scope.addToSelection(d, $scope.negative_selection);
    })
      });
    $scope.removeFromSelection = function (item, sel) {
        if ($scope.isInSelection(item, sel)) {
            for (var n = 0; n < sel.length; n++) {
                if (sel[n].uid == item.uid) {
                    sel.splice(n, 1);
                    break;
                }
            }
            logEvent('remove_selection');
        }
        updateCookies();
        updateState();
    };
    $scope.resetSelections = function () {
        $scope.current_selection = [];
        $scope.negative_selection = [];
        updateCookies();
        updateState();
        logEvent('reset_selection');
    };
    function loadCookies() {
        $scope.current_selection = [];
        $scope.negative_selection = [];
        loadElementsFromIdList($cookies.getObject('current_selection_ids'), $scope.current_selection);
        loadElementsFromIdList($cookies.getObject('negative_selection_ids'), $scope.negative_selection);
    }

    function updateCookies() {
        $cookies.putObject('current_selection_ids', $scope.getIdList($scope.current_selection));
        $cookies.putObject('negative_selection_ids', $scope.getIdList($scope.negative_selection));
    }

    function updateState() {
        var new_params = {
            q: $scope.getIdList($scope.current_selection),
            n: $scope.getIdList($scope.negative_selection),
            image_url: null
        };
        $state.go($state.current.name, new_params, {notify: false});
    }

    function loadElementsFromIdList(ids, resultArr) {
        if (ids !== undefined) {
            for (var n = 0; n < ids.length; n++)
                $http.get('api/element/' + ids[n]).then(
                    function (response) {
                        resultArr.push(response.data);
                        updateState();
                    }, function (response) {
                        $scope.showSimpleToast("Error retrieving element : " + response.status + " " + response.data);
                    });
        }
    }

    $scope.goToGraph = function() {
        var image_uids = [];
        for (var n = 0; n < $scope.current_selection.length; n++){
            image_uids.push($scope.current_selection[n].images[0].uid);
        }
        $state.go('graph', {uid: image_uids});
    };


        function parseParams(param) {
            if (param == null)
                return [];
            if (param instanceof Array)
                return param;
            return [param];
        }

    function logEvent(evt, evt_data) {
        $http.post(
            'api/log',
            {
                data: {
                    event: evt,
                    event_data: evt_data,
                    scope_data: {
                        current_selection: $scope.current_selection.map(function(e) {return e.images[0].uid}),
                        negative_selection: $scope.negative_selection.map(function(e) {return e.images[0].uid}),
                        show_side_query: $scope.showSideQuery,
                        show_results_as_embedding: $scope.showResultsAsEmbedding,
                        nb_desired_results: $scope.nbResults,
                        nb_obtained_results: $scope.results.length,
                        nb_results_displayed: $scope.resultsDisplayed
                    },
                    timestamp: (new Date()).getTime()
                }
            }
        )
    }
});
