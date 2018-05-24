/**
 * Created by benoit on 24/07/2017.
 */

angular.module('replicaModule').directive('imgBox', function() {

    function getImageThumbnail(e) {
        return e.iiif_url + "/full/450,/0/default.jpg";
    }

    function makePercent(v) {
        if (v)
            return (v*100)+'%';
        else
            return "";
    }

    return {
        templateNamespace: 'svg',
        scope: {
            displayElement: '=element',
            displaySize: '='
        },
        template:
        '<svg in-view="$inview&&loadImage()"' +
        'ng-attr-height="{{displaySize}}" ng-attr-width="{{displaySize}}"">' +
        '<image ng-href="{{imageSrc}}" xlink:href="" width="100%" height="100%"></image>' +
        '<rect ng-if="has_box()"' +
        'ng-attr-x="{{ get_x() }}" ng-attr-y="{{ get_y() }}"' +
        'ng-attr-height="{{ get_height() }}" ng-attr-width="{{ get_width() }}"' +
        'style="stroke:red;stroke-width:2;fill-opacity:0"></rect>' +
        '</svg> ',
        link: function (scope, element, attrs) {
            var relativeHeight=0, relativeWidth=0;
            scope.image = new Image();
            scope.image.onload = function () {
                scope.$apply(function () {
                    scope.imageWidth = scope.image.width;
                    scope.imageHeight = scope.image.height;

                    if (scope.imageHeight>scope.imageWidth) {
                        relativeHeight = 1;
                        relativeWidth = scope.imageWidth/scope.imageHeight;
                    } else {
                        relativeWidth = 1;
                        relativeHeight = scope.imageHeight/scope.imageWidth;
                    }
                    scope.imageSrc = getImageThumbnail(scope.displayElement);
                });
            };
            scope.imageSrc = "loader.gif";
            var loading = false;
            scope.loadImage = function() {
                if (!loading) {
                    scope.image.src = getImageThumbnail(scope.displayElement);
                    loading=true;
                }
            };
            scope.$watch('displayElement.uid', function() {
                scope.imageSrc = "loader.gif";
                if (loading) {
                    loading = false;
                    scope.loadImage();
                }
            });
            scope.has_box = function() {return angular.isDefined(scope.displayElement.box);};
            scope.get_x = function() { return makePercent(0.5-relativeWidth/2 + scope.displayElement.box.x*relativeWidth); };
            scope.get_y = function() { return makePercent(0.5-relativeHeight/2 + scope.displayElement.box.y*relativeHeight); };
            scope.get_width = function() { return makePercent(scope.displayElement.box.w*relativeWidth); };
            scope.get_height = function() { return makePercent(scope.displayElement.box.h*relativeHeight); };
        }
    }
});

angular.module('replicaModule').directive('infiniteScroll', [ "$window", function ($window) {
    return {
        link:function (scope, element, attrs) {
            var offset = parseInt(attrs.threshold) || 10;
            var e = element[0];

            angular.element($window).bind('scroll', function () {
                if ($window.innerHeight >= e.getBoundingClientRect().bottom - offset) {
                    scope.$apply(attrs.infiniteScroll);
                }
            });
        }
    };
}]);

angular.module('replicaModule').filter('strLimit', ['$filter', function($filter) {
   return function(input, limit) {
      if (! input) return;
      if (input.length <= limit) {
          return input;
      }

      return $filter('limitTo')(input, limit) + '...';
   };
}]);