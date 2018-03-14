replicaModule.controller('searchController', function ($scope, $http, $mdDialog, $cookies, $state, $stateParams, $analytics) {
    $scope.results = [];
    $scope.filteredResults = [];
    $scope.links = [];
    $scope.showSideQuery = true;
    $scope.searchQuery = '';
    $scope.minDate = null;
    $scope.maxDate = null;
    $scope.showResultsAsEmbedding = false;
    $scope.findAllTermsInText = true;
    $scope.nbResults = 250;
    $scope.indexKey = null;
    $scope.experiment_mode = false;
    $scope.experiment_type = '';
    $scope.experiment_id = 0;
    $scope.limitFilteredResults = null;
    $scope.filterImageSearchMetadata = false;
    $scope.imageSearchRerank = true;
    $scope.totalSearched = 0;
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

    function updateLinks() {
        $http.post('api/link/related',
            {
                image_uids: $scope.results.map(function (e) {
                    return e.images[0].uid
                }),
                personal: $scope.experiment_mode
            }).then(
            function (response) {
                $scope.links = response.data.links;
                $scope.links.forEach(function (l) {
                    var sourceNode = $scope.results.filter(function (d, i) {
                        return d.images[0].uid == l.source
                    })[0];
                    var targetNode = $scope.results.filter(function (d, i) {
                        return d.images[0].uid == l.target
                    })[0];
                    l.source = sourceNode;
                    l.target = targetNode;
                });
            }, function (response) {
                $scope.showErrorToast("Links updating failed", response);
            })
    }

    function updateFilteredResults() {
        $scope.filteredResults = $scope.results.filter(function (d, i) {
            var return_value = true;
            $scope.current_selection.forEach(function (d2) {
                if (d2.uid == d.uid) return_value = false;
            });
            $scope.negative_selection.forEach(function (d2) {
                if (d2.uid == d.uid) return_value = false;
            });
            return return_value;
        });
        if ($scope.limitFilteredResults) {
            $scope.filteredResults = $scope.filteredResults.slice(0, $scope.limitFilteredResults);
        }
    }

    $scope.$watch('results', updateLinks);
    $scope.$watch('results', updateFilteredResults);

    function makeMetadataRequest() {
        return {
            query: $scope.searchQuery,
            nb_results: $scope.nbResults,
            all_terms: $scope.findAllTermsInText ? 1 : 0,
            min_date: $scope.minDate,
            max_date: $scope.maxDate
        };
    }

    $scope.getRandom = function () {
        var request = makeMetadataRequest();
        $http.get('api/element/random',
            {params: {'nb_elements': $scope.nbResults}}).then(
            function (response) {
                $scope.results = response.data;
                $scope.resultsDisplayed = resultsDisplayedInitial;
                $scope.totalSearched = response.data.total;
            }, function (response) {
                $scope.showErrorToast("Search failed", response);
            }).finally(
            function () {
                $analytics.eventTrack('getRandom');
                logEvent('get_random', request);
            }
        )
    };
    $scope.searchText = function () {
        var request = makeMetadataRequest();
        $http.get('api/search/text',
            {params: request}).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
                $scope.totalSearched = response.data.total;
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
            positive_image_uids: positive_image_ids,
            negative_image_uids: negative_image_ids,
            nb_results: $scope.nbResults,
            index: $scope.indexKey,
            rerank: $scope.imageSearchRerank
        };
        if ($scope.filterImageSearchMetadata) {
            request.metadata = makeMetadataRequest();
        }
        $http.post("/api/image/search", request).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
                $scope.totalSearched = response.data.total;
            }, function (response) {
                $scope.showErrorToast("Search failed", response);
            }
        ).finally(
            function () {
                $scope.is_searching = false;
                for (i = 0; i < $scope.current_selection.length; i++) {
                    delete $scope.current_selection[i].images[0].box;
                }

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
            "reranking_results": 4000,
            "index": $scope.indexKey
        };
        if ($scope.filterImageSearchMetadata) {
            request.metadata = makeMetadataRequest();
        }
        $http.post("/api/image/search_region", request, {timeout: 20000}).then(
            function (response) {
                $scope.results = response.data.results;
                $scope.resultsDisplayed = resultsDisplayedInitial;
                $scope.showResultsAsEmbedding = false;
                $scope.totalSearched = response.data.total;
            }, function (response) {
                $scope.showErrorToast("Search failed", response.status);
            }
        ).finally(
            function () {
                $scope.is_searching = false;
                $analytics.eventTrack('searchImageRegion');
                logEvent('search_region', request);
            }
        );
    };
    $scope.showMoreResults = function () {
        $scope.resultsDisplayed += resultsDisplayedInitial;
    };
    $scope.addToGroup = function () {
        //fetch groups
        $http.get('api/user/groups').then(
            function(response) {
                add_group_dialog(response.data.groups);
            },
            function(response) {
                $scope.showErrorToast('Could not retrieve groups', response);
            }
        );
        function add_group_dialog(groups) {
            $mdDialog.show({
                template: '<md-dialog>' +
                '  <md-dialog-content>' +
                '   <div>' +
                '   <h3>Create a new group</h3>' +
                '   <md-input-container>' +
                '       <label>Group Label</label>' +
                '       <input ng-model="group_label" required>' +
                '   </md-input-container>' +
                '   <md-button type="submit" ng-click="createGroup()" class="md-raised md-primary">Create Group</md-button>' +
                '   </div>' +
                '   <div flex="row" ng-repeat="link in links">' +
                '       <img-box element="link.img1" display-size="200"></img-box>' +
                '       <img-box element="link.img2" display-size="200"></img-box>' +
                '       <span>{{ link.type }}</span>' +
                '       <span>{{ link.status }}</span>' +
                '   <md-divider></md-divider>' +
                '   </div>' +
                '   <div ng-if="groups.length>0">' +
                '       <h3>Add to an existing group</h3>' +
                '       <md-radio-group ng-model="selected_group_uid">' +
                '           <md-radio-button ng-repeat="g in groups" \
                                   ng-value="g.uid">{{g.label}} ({{g.nb_images}} images)</md-radio-button>' +
                '       </md-radio-group>' +
                '       <md-button ng-click="addToGroup(selected_group_uid)" class="md-raised md-primary">Add To Existing Group</md-button>' +
                '   </div>' +
                '</md-dialog-content>' +
                '  <md-dialog-actions>' +
                '    <md-button ng-click="closeDialog()" class="md-primary">' +
                '      Cancel' +
                '    </md-button>' +
                '  </md-dialog-actions>' +
                '</md-dialog>',
                locals: {rootScope: $scope},
                controller: function ($http, $mdDialog, $scope, rootScope) {
                    $scope.groups = groups;
                    $scope.selected_group_uid = null;
                    $scope.group_label = '';
                    if (groups.length>0)
                        $scope.selected_group_uid = groups[0].uid;

                    function getImageUids() {
                        return rootScope.current_selection.map(function(cho) {return cho.images[0].uid;});
                    }

                    $scope.closeDialog = function() {
                        $mdDialog.hide();
                    };
                    $scope.createGroup = function() {
                        var request = {
                            label: $scope.group_label,
                            image_uids: getImageUids()
                        };
                        $http.post('api/group', request).then(
                            function(response) {
                                rootScope.showSimpleToast('Group added');
                                $mdDialog.hide();
                            },
                            function(response) {
                                rootScope.showErrorToast('Operation Failed', response);
                            }
                        )
                    };
                    $scope.addToGroup = function(group_uid) {
                        $http.post('api/group/'+group_uid+'/add', {image_uids: getImageUids()}).then(
                            function(response) {
                                rootScope.showSimpleToast('Added to group');
                                $mdDialog.hide();
                            },
                            function(response) {
                                rootScope.showErrorToast('Operation Failed', response);
                            }
                        )
                    }
                }
            });
        }
    };
    $scope.addAnnotation = function () {
        function save_links_dialog(link_type) {
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
                '    <md-button ng-click="closeDialog(false)" class="md-primary">' +
                '      Close' +
                '    </md-button>' +
                '    <md-button ng-click="closeDialog(true)" class="md-primary">' +
                '      Close and Clear Selection' +
                '    </md-button>' +
                '  </md-dialog-actions>' +
                '</md-dialog>',
                locals: {rootScope: $scope},
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
                                status: ""
                            })
                        }
                    }
                    for (var n = 0; n < rootScope.current_selection.length; n++) {
                        for (var m = 0; m < rootScope.negative_selection.length; m++) {
                            $scope.links.push({
                                img1: rootScope.current_selection[n].images[0],
                                img2: rootScope.negative_selection[m].images[0],
                                type: 'NEGATIVE',
                                status: ""
                            })
                        }
                    }
                    // Saving functions
                    for (var n = 0; n < $scope.links.length; n++) {
                        $scope.links[n].create = function () {
                            this.status = 'SENDING';
                            var l = this;
                            var request = {
                                img1_uid: this.img1.uid,
                                img2_uid: this.img2.uid,
                                type: this.type,
                                personal: rootScope.experiment_mode
                            };
                            $http.post('api/link/create',
                                request
                            ).then(function () {
                                    l.status = 'ADDED';
                                    logEvent('link_create', request)
                                }
                                , function (response) {
                                    l.status = 'ERROR : ' + response.data.message;
                                })
                        };
                    }
                    $scope.closeDialog = function (clearSelection) {
                        $mdDialog.hide();
                        updateLinks();
                        if (clearSelection)
                            rootScope.resetSelections();
                    };
                    $scope.saveAll = function () {
                        $scope.saving_started = true;
                        for (var i = 0; i < $scope.links.length; i++) {
                            $scope.links[i].create();
                        }
                    };
                }
            });
        }

        if ($scope.experiment_mode)
            save_links_dialog('TO BE ADDED');
        else
            // Allow the user to pick the type of links to be added
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
                locals: {rootScope: $scope},
                controller: function ($mdDialog, $scope, rootScope) {
                    $scope.POSSIBLE_TYPES = ['DUPLICATE', 'POSITIVE'];
                    $scope.closeDialog = function (link_type) {
                        $mdDialog.hide(link_type);
                    };
                    $scope.cancelDialog = function () {
                        $mdDialog.cancel();
                    };
                }
            }).then(save_links_dialog)
    };
    $scope.addToSelection = function (item, sel) {
        if (!$scope.isInSelection(item, sel)) {
            copied_item = angular.copy(item);
            delete copied_item.images[0].box;
            sel.push(copied_item);
            logEvent('add_selection');
        }
        updateCookies();
        updateState();
    };
    $scope.$on('toggleCurrentSelection', function (evt, d) {
        if ($scope.isInSelection(d, $scope.negative_selection))
            return;
        $scope.$apply(function () {
            if ($scope.isInSelection(d, $scope.current_selection))
                $scope.removeFromSelection(d, $scope.current_selection);
            else
                $scope.addToSelection(d, $scope.current_selection);
        })
    });
    $scope.$on('toggleNegativeSelection', function (evt, d) {
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

    $scope.goToGraph = function () {
        var image_uids = [];
        for (var n = 0; n < $scope.current_selection.length; n++) {
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
                        current_selection: $scope.current_selection.map(function (e) {
                            return e.images[0].uid
                        }),
                        negative_selection: $scope.negative_selection.map(function (e) {
                            return e.images[0].uid
                        }),
                        show_side_query: $scope.showSideQuery,
                        show_results_as_embedding: $scope.showResultsAsEmbedding,
                        nb_desired_results: $scope.nbResults,
                        nb_obtained_results: $scope.results.length,
                        nb_results_displayed: $scope.resultsDisplayed,
                        index: $scope.indexKey,
                        experiment_id: $scope.experiment_id
                    },
                    timestamp: (new Date()).getTime()
                }
            }
        )
    }

    if ($stateParams.expmode != null) {
        $scope.experiment_mode = true;
        $scope.experiment_id = $stateParams.expmode;
        if ($stateParams.expmode >= 100) {
            // Annotation task
            $scope.experiment_type = 'annotation';
            $scope.showResultsAsEmbedding = true;
            $scope.nbResults = 400;
            if ($stateParams.expmode == 101) {
                $scope.indexKey = 'canaletto_guardi';
                $scope.searchQuery = 'canaletto';
            }
            if ($stateParams.expmode == 102) {
                $scope.indexKey = 'untrained';
                $scope.searchQuery = 'canaletto';
            }
            if ($stateParams.expmode == 103) {
                $scope.indexKey = 'tiziano';
                $scope.searchQuery = 'tiziano';
            }
            if ($stateParams.expmode == 104) {
                $scope.indexKey = 'untrained';
                $scope.searchQuery = 'tiziano';
            }
            if ($stateParams.expmode == 105) {
                $scope.indexKey = 'allegory';
                $scope.searchQuery = 'allegory';
            }
            if ($stateParams.expmode == 106) {
                $scope.indexKey = 'untrained';
                $scope.searchQuery = 'allegory';
            }
            if ($stateParams.expmode == 107) {
                $scope.indexKey = 'diana';
                $scope.searchQuery = 'diana apollo';
                $scope.findAllTermsInText = false;
            }
            if ($stateParams.expmode == 108) {
                $scope.indexKey = 'untrained';
                $scope.searchQuery = 'diana';
            }
            $scope.searchText();
            $scope.resetSelections();
            logEvent('start_experiment',
                {
                    type: 'annotation',
                    query: $scope.searchQuery,
                    index: $scope.indexKey
                })
        } else {
            // Search task
            $scope.experiment_type = 'search';
            // Paintings in paintings
            var initial_query = '0a70bff61b184246bf75992ad0168483';
            if ($stateParams.expmode == 1) {
                $scope.indexKey = 'algebraic';
                initial_query = '0a70bff61b184246bf75992ad0168483';
            }
            if ($stateParams.expmode == 2) {
                $scope.indexKey = 'untrained';
                initial_query = '0a70bff61b184246bf75992ad0168483';
            }

            // Crucifixion with 3 crosses
            if ($stateParams.expmode == 3) {
                $scope.indexKey = 'algebraic';
                initial_query = 'd844306bd69e4ad09e8ecdd29f22a3b0';
            }
            if ($stateParams.expmode == 4) {
                $scope.indexKey = 'untrained';
                initial_query = 'd844306bd69e4ad09e8ecdd29f22a3b0';
            }

            // Still life with a skull
            if ($stateParams.expmode == 5) {
                $scope.indexKey = 'algebraic';
                initial_query = '30ab745bd7a8478fa9f1f64080b0b955';
            }
            if ($stateParams.expmode == 6) {
                $scope.indexKey = 'untrained';
                initial_query = '30ab745bd7a8478fa9f1f64080b0b955';
            }

            if ($stateParams.expmode == 9) {
                $scope.indexKey = 'algebraic';
                initial_query = '0c6006b8c9024b53954fc4f92a631b1b';
            }

            $scope.current_selection = [];
            $scope.negative_selection = [];
            $scope.limitFilteredResults = 30;
            $scope.nbResults = 120;
            loadElementsFromIdList([initial_query], $scope.current_selection);
            logEvent('start_experiment',
                {
                    type: 'search',
                    initial_query: initial_query,
                    index: $scope.indexKey
                })
        }
    }
    if ($stateParams.index != null)
        $scope.indexKey = $stateParams.index;
});
